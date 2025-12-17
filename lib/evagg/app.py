import logging
import asyncio

from lib.evagg.llm import OpenAIClient
from lib.evagg.content import (
    PromptBasedContentExtractor,
    HGVSVariantComparator,
    HGVSVariantFactory,
    ObservationFinder,
)
from lib.evagg.ref import (
    ClinvarClient,
    GnomadClient,
    MutalyzerClient,
    NcbiLookupClient,
    WebHPOClient,
    PyHPOClient,
    RefSeqLookupClient,
    VepClient,
)
from lib.evagg.utils.web import RequestsWebContentClient, WebClientSettings
from lib.evagg.ref.ncbi import get_ncbi_response_translator
from typing import Dict, Sequence
from lib.evagg.pdf.parse import parse_content
from lib.evagg.types.prompt_tag import PromptTag

logger = logging.getLogger(__name__)


class App:
    def __init__(
        self,
        content: bytes,
        gene_symbol: str,
    ) -> None:
        self._content = content
        self._gene_symbol = gene_symbol
        self._ncbi_lookup_client = NcbiLookupClient(
            web_client=RequestsWebContentClient(
                WebClientSettings(status_code_translator=get_ncbi_response_translator())
            )
        )
        self._vep_client = VepClient(web_client=RequestsWebContentClient())
        self._clinvar_client = ClinvarClient(web_client=RequestsWebContentClient())
        self._gnomad_client = GnomadClient(web_client=RequestsWebContentClient())
        self._llm_client = OpenAIClient()
        self._extractor = PromptBasedContentExtractor(
            fields=[
                'evidence_id',
                'gene',
                'paper_id',
                'hgvs_c',
                'hgvs_p',
                'paper_variant',
                'transcript',
                'validation_error',
                'individual_id',
                'phenotype',
                'zygosity',
                'variant_inheritance',
                'variant_type',
                'study_type',
                'engineered_cells',
                'patient_cells_tissues',
                'animal_model',
                'citation',
                'link',
                'paper_title',
            ],
            llm_client=self._llm_client,
            phenotype_searcher=WebHPOClient(
                web_client=RequestsWebContentClient(),
            ),
            phenotype_fetcher=PyHPOClient(),
            observation_finder=ObservationFinder(
                llm_client=self._llm_client,
                variant_factory=HGVSVariantFactory(
                    mutalyzer_client=MutalyzerClient(
                        web_client=RequestsWebContentClient(
                            WebClientSettings(
                                no_raise_codes=[422],
                            )
                        )
                    ),
                    ncbi_lookup_client=self._ncbi_lookup_client,
                    refseq_client=RefSeqLookupClient(
                        web_client=RequestsWebContentClient(
                            WebClientSettings(
                                status_code_translator=get_ncbi_response_translator()
                            )
                        )
                    ),
                ),
                variant_comparator=HGVSVariantComparator(),
            ),
        )

    def execute(self) -> Sequence[Dict[str, str | None]]:
        paper = parse_content(self._content)
        title = asyncio.run(
            self._llm_client.prompt_json_from_string(
                user_prompt=f"""
                Extract the title of the following (truncated to 1000 characters) scientific paper.

                Return your response as a JSON object like this:
                {{
                    "title": "The title of the paper"
                }}

                Paper: {paper.fulltext_md[:1000]}
            """,
                prompt_tag=PromptTag.TITLE,
            )
        )['title']
        pmids = self._ncbi_lookup_client.search(
            title + '[ti]',
        )
        if pmids:
            paper = self._ncbi_lookup_client.fetch(pmids[0], paper)
        extracted_observations = self._extractor.extract(paper, self._gene_symbol)
        for extracted_observation in extracted_observations:
            self._vep_client.enrich(extracted_observation)
            self._clinvar_client.enrich(extracted_observation)
            self._gnomad_client.enrich(extracted_observation)
        return extracted_observations
