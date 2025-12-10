import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Sequence, Tuple

from lib.evagg.llm import OpenAIClient
from lib.evagg.types import Paper, PromptTag
from lib.evagg.ref import PyHPOClient, WebHPOClient

from .observation import Observation, ObservationFinder

logger = logging.getLogger(__name__)


def _get_prompt_file_path(name: str) -> str:
    return os.path.join(os.path.dirname(__file__), "prompts", f"{name}.txt")


class PromptBasedContentExtractor:
    _PROMPT_FIELDS = {
        "phenotype": _get_prompt_file_path("phenotypes_all"),
        "zygosity": _get_prompt_file_path("zygosity"),
        "variant_inheritance": _get_prompt_file_path("variant_inheritance"),
        "variant_type": _get_prompt_file_path("variant_type"),
        "engineered_cells": _get_prompt_file_path("functional_study"),
        "patient_cells_tissues": _get_prompt_file_path("functional_study"),
        "animal_model": _get_prompt_file_path("functional_study"),
        "study_type": _get_prompt_file_path("study_type"),
    }
    # These are the expensive prompt fields we should cache per paper.
    _CACHE_VARIANT_FIELDS = ["variant_type", "functional_study"]
    _CACHE_INDIVIDUAL_FIELDS = ["phenotype"]
    _CACHE_PAPER_FIELDS = ["study_type"]

    def __init__(
        self,
        fields: Sequence[str],
        llm_client: OpenAIClient,
        observation_finder: ObservationFinder,
        phenotype_searcher: WebHPOClient,
        phenotype_fetcher: PyHPOClient,
    ) -> None:
        self._fields = fields
        self._llm_client = llm_client
        self._observation_finder = observation_finder
        self._phenotype_searcher = phenotype_searcher
        self._phenotype_fetcher = phenotype_fetcher

    def _get_lookup_field(
        self, gene_symbol: str, paper: Paper, ob: Observation, field: str
    ) -> Tuple[str, str]:
        def get_link() -> str:
            return (
                f"https://www.ncbi.nlm.nih.gov/pmc/articles/{paper.props['pmcid']}"
                if paper.props.get("pmcid")
                else paper.props.get("link", "")
            )

        def get_hgvs_c() -> str:
            return (
                ob.variant.hgvs_desc
                if not ob.variant.hgvs_desc.startswith("p.")
                else "NA"
            )

        def get_hgvs_p() -> str:
            if ob.variant.protein_consequence:
                return ob.variant.protein_consequence.hgvs_desc
            return (
                ob.variant.hgvs_desc if ob.variant.hgvs_desc.startswith("p.") else "NA"
            )

        field_map = {
            "evidence_id": lambda: ob.variant.get_unique_id(paper.id, ob.individual),
            "gene": lambda: gene_symbol,
            "paper_id": lambda: paper.id,
            "citation": lambda: paper.props.get("citation", ""),
            "source_type": lambda: "fulltext"
            if paper.props.get("fulltext_xml")
            else "abstract",
            "link": get_link,
            "paper_title": lambda: paper.props.get("title", ""),
            "hgvs_c": get_hgvs_c,
            "hgvs_p": get_hgvs_p,
            "paper_variant": lambda: ", ".join(ob.variant_descriptions),
            "transcript": lambda: ob.variant.refseq or "unknown",
            "valid": lambda: str(ob.variant.valid),
            "validation_error": lambda: ob.variant.validation_error or "",
            "individual_id": lambda: ob.individual,
            "gnomad_frequency": lambda: "unknown",
        }

        if field not in field_map:
            raise ValueError(f"Unsupported field: {field}")

        return field, field_map[field]()

    async def _convert_phenotype_to_hpo(self, phenotype: List[str]) -> List[str]:
        """Convert a list of unstructured phenotype descriptions to HPO/OMIM terms."""
        if not phenotype:
            return []

        match_dict = {}

        # Any descriptions that look like valid HPO terms themselves should be validated.
        for term in phenotype.copy():
            ids = re.findall(r"\(?[Hh][Pp]:\d+\)?", term)
            if ids:
                hpo_id = ids[0]
                id_result = self._phenotype_fetcher.fetch(hpo_id.strip("()").upper())
                if id_result:
                    phenotype.remove(term)
                    match_dict[term] = f"{id_result['name']} ({id_result['id']})"

        async def _get_match_for_term(term: str) -> str | None:
            result = self._phenotype_searcher.search(query=term, retmax=10)

            candidates = set()
            for i in range(len(result)):
                candidate = f"{result[i]['name']} ({result[i]['id']}) - {result[i]['definition']}"
                if result[i]["synonyms"]:
                    candidate += f" - Synonymous with {result[i]['synonyms']}"
                candidates.add(candidate)

            if candidates:
                response = await self._llm_client.prompt_json(
                    prompt_filepath=_get_prompt_file_path("phenotypes_candidates"),
                    params={"term": term, "candidates": "\n".join(candidates)},
                    prompt_tag=PromptTag.PHENOTYPES_CANDIDATES,
                )
                return response.get("match")

            return None

        # Alternatively, search for the term in the HPO database, use AOAI to determine which of the results appears
        # to be the best match.
        for term in phenotype.copy():
            match = await _get_match_for_term(term)
            if match:
                match_dict[term] = match
                phenotype.remove(term)

        # Before we give up, try again with a simplified version of the term.
        for term in phenotype.copy():
            response = await self._llm_client.prompt_json(
                prompt_filepath=_get_prompt_file_path("phenotypes_simplify"),
                params={"term": term},
                prompt_tag=PromptTag.PHENOTYPES_SIMPLIFY,
            )

            if simplified := response.get("simplified"):
                match = await _get_match_for_term(simplified)
                if match:
                    match_dict[f"{term} (S)"] = match
                    phenotype.remove(term)

        all_values = list(match_dict.values())
        logger.info(f"Converted phenotypes: {match_dict}")

        if phenotype:
            logger.warning(f"Failed to convert phenotypes: {phenotype}")
            all_values.extend(phenotype)

        return list(set(all_values))

    async def _observation_phenotypes_for_text(
        self,
        text: str,
        description: str,
        gene_symbol: str,
    ) -> List[str]:
        all_phenotypes_result = await self._llm_client.prompt_json(
            self._PROMPT_FIELDS["phenotype"],
            {"passage": text},
            PromptTag.PHENOTYPES_ALL,
            # "max_output_tokens": 4096,
        )
        if (all_phenotypes := all_phenotypes_result.get("phenotypes", [])) == []:
            return []

        # Potentially consider linked observations like comp-hets?
        observation_phenotypes_params = {
            "gene": gene_symbol,
            "passage": text,
            "observation": description,
            "candidates": ", ".join(all_phenotypes),
        }
        observation_phenotypes_result = await self._llm_client.prompt_json(
            _get_prompt_file_path("phenotypes_observation"),
            observation_phenotypes_params,
            PromptTag.PHENOTYPES_OBSERVATION,
        )
        if (
            observation_phenotypes := observation_phenotypes_result.get(
                "phenotypes", []
            )
        ) == []:
            return []

        observation_acronymns_result = await self._llm_client.prompt_json(
            _get_prompt_file_path("phenotypes_acronyms"),
            {"passage": text, "phenotypes": ", ".join(observation_phenotypes)},
            PromptTag.PHENOTYPES_ACRONYMS,
        )

        return observation_acronymns_result.get("phenotypes", [])

    async def _generate_phenotype_field(
        self, gene_symbol: str, observation: Observation
    ) -> str:
        # Obtain all the phenotype strings listed in the text associated with the gene.
        fulltext = "\n\n".join([t.text for t in observation.texts])
        # TODO: treating all tables in paper as a single text, maybe this isn't ideal, consider grouping by 'id'
        table_texts = "\n\n".join(
            [t.text for t in observation.texts if t.section_type == "TABLE"]
        )

        # Determine the phenotype strings that are associated specifically with the observation.
        v_sub = ", ".join(observation.variant_descriptions)
        if observation.patient_descriptions != ["unknown"]:
            p_sub = ", ".join(observation.patient_descriptions)
            obs_desc = f"the patient described as {p_sub} who possesses the variant described as {v_sub}."
        else:
            obs_desc = f"the variant described as {v_sub}."

        # Run phenotype extraction for all the texts of interest.
        texts = [fulltext]
        if table_texts != "":
            texts.append(table_texts)
        result = await asyncio.gather(
            *[
                self._observation_phenotypes_for_text(t, obs_desc, gene_symbol)
                for t in texts
            ]
        )
        observation_phenotypes = list(
            {item.lower() for sublist in result for item in sublist}
        )

        # Now convert this phenotype list to OMIM/HPO ids.
        structured_phenotypes = await self._convert_phenotype_to_hpo(
            observation_phenotypes
        )

        # Duplicates are conceivable, get unique set again.
        return "; ".join(set(structured_phenotypes))

    async def _run_field_prompt(
        self, gene_symbol: str, observation: Observation, field: str
    ) -> Dict[str, Any]:
        params = {
            # First element is full text of the observation, consider alternatives
            "passage": "\n\n".join([t.text for t in observation.texts]),
            "variant_descriptions": ", ".join(observation.variant_descriptions),
            "patient_descriptions": ", ".join(observation.patient_descriptions),
            "gene": gene_symbol,
        }
        return await self._llm_client.prompt_json(
            prompt_filepath=self._PROMPT_FIELDS[field],
            params=params,
            prompt_tag=PromptTag(field),
        )

    async def _generate_basic_field(
        self, gene_symbol: str, observation: Observation, field: str
    ) -> str:
        result = (await self._run_field_prompt(gene_symbol, observation, field)).get(
            field, "failed"
        )
        # result can be a string or a json object.
        if not isinstance(result, str):
            result = json.dumps(result)
        return result

    async def _generate_functional_study_field(
        self, gene_symbol: str, observation: Observation, field: str
    ) -> str:
        result = await self._run_field_prompt(gene_symbol, observation, field)
        func_studies = result.get("functional_study", [])

        # Note the prompt uses a different set of strings to represent the study types found, so we need to map them.
        study_type_map = {
            "engineered_cells": "cell line",
            "patient_cells_tissues": "patient cells",
            "animal_model": "animal model",
            "none": "none",
        }

        return "True" if (study_type_map[field] in func_studies) else "False"

    async def _generate_prompt_field(
        self, gene_symbol: str, observation: Observation, field: str
    ) -> str:
        if field == "phenotype":
            return await self._generate_phenotype_field(gene_symbol, observation)
        elif field in ["engineered_cells", "patient_cells_tissues", "animal_model"]:
            return await self._generate_functional_study_field(
                gene_symbol, observation, field
            )
        else:
            return await self._generate_basic_field(gene_symbol, observation, field)

    async def _get_fields(
        self,
        gene_symbol: str,
        paper: Paper,
        ob: Observation,
        cache: Dict[Any, asyncio.Task],
    ) -> Dict[str, str]:
        def _get_key(ob: Observation, field: str) -> Any:
            if field in self._CACHE_VARIANT_FIELDS:
                return (ob.variant, field)
            elif field in self._CACHE_INDIVIDUAL_FIELDS and ob.individual != "unknown":
                return (ob.individual, field)
            elif field in self._CACHE_PAPER_FIELDS:
                # Paper instance is implicit.
                return field
            return None

        async def _get_prompt_field(field: str) -> Tuple[str, str]:
            # Use a cached task for variant fields if available.
            key = _get_key(ob, field)
            if key and key in cache:
                prompt_task = cache[key]
                logger.info(f"Using cached task for {key}")
            else:
                # Create and schedule a prompt task to get the prompt field.
                prompt_task = asyncio.create_task(
                    self._generate_prompt_field(gene_symbol, ob, field)
                )

                if key:
                    cache[key] = prompt_task

            # Get the value from the completed task.
            value = await prompt_task
            return field, value

        lookup_fields = [f for f in self._fields if f not in self._PROMPT_FIELDS]
        prompt_fields = [f for f in self._fields if f in self._PROMPT_FIELDS]
        # Collect all the non-prompt-based fields field values via lookup on the paper/observation objects.
        fields = dict(
            self._get_lookup_field(gene_symbol, paper, ob, f) for f in lookup_fields
        )
        # Collect the remaining prompt-based fields with LLM calls in parallel.
        fields.update(
            await asyncio.gather(*[_get_prompt_field(f) for f in prompt_fields])
        )
        return fields

    async def _extract_fields(
        self, paper: Paper, gene_symbol: str, obs: Sequence[Observation]
    ) -> List[Dict[str, str]]:
        # TODO - because the returned observations include the text associated with each observation, it's not trivial
        # to pre-cache the variant level fields. We don't have any easy way to collect all the unique texts associated
        # with all observations of the same variant (but different individuals). As a temporary solution, we'll cache
        # the first finding of a variant-level result and use that only. This will not be robust to scenarios where the
        # texts associated with multiple observations of the same variant differ.
        cache: Dict[Any, asyncio.Task] = {}
        return await asyncio.gather(
            *[self._get_fields(gene_symbol, paper, ob, cache) for ob in obs]
        )

    def extract(self, paper: Paper, gene_symbol: str) -> Sequence[Dict[str, str]]:
        # Find all the observations in the paper relating to the query.
        observations = asyncio.run(
            self._observation_finder.find_observations(gene_symbol, paper)
        )
        if not observations:
            logger.info(f"No observations found in {paper.id} for {gene_symbol}")
            return []

        # Extract all the requested fields from the observations.
        logger.info(
            f"Found {len(observations)} observations in {paper.id} for {gene_symbol}"
        )
        return asyncio.run(self._extract_fields(paper, gene_symbol, observations))
