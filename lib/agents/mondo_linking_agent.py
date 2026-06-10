"""Tool-using agent for MONDO disease linking."""

import json
from typing import Literal

from agents import Agent, function_tool
from pydantic import BaseModel, Field

from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
from lib.core.environment import env
from lib.models.evidence_block import ReasoningBlock
from lib.reference_data import mondo


class MondoAgentDecision(BaseModel):
    """The MONDO linker's final decision."""

    mondo_id: str | None = Field(
        default=None,
        description='Selected MONDO identifier, or null when no supported match exists.',
    )
    term: str | None = Field(
        default=None,
        description='Selected MONDO label, or null when no supported match exists.',
    )
    confidence: Literal['high', 'medium', 'low'] | None = None


@function_tool
def get_mondo_term(mondo_id: str, include_relations: bool = True) -> dict:
    """Fetch MONDO term information by MONDO ID."""
    term = mondo.get_mondo_term(mondo_id, include_relations=include_relations)
    if term is None:
        raise ValueError(f'MONDO term {mondo_id} not found')
    return term


@function_tool
def search_mondo_terms(
    query: str,
    limit: int = 10,
) -> list[dict]:
    """Search MONDO labels and synonyms for candidate terms."""
    return mondo.search_mondo_terms(query, limit=limit)


@function_tool
def get_mondo_by_identifier(identifier: str) -> list[dict]:
    """Fetch MONDO terms by MONDO ID, OBO IRI, OMIM, Orphanet, or other xref."""
    return mondo.get_mondo_by_identifier(identifier)


@function_tool
def get_mondo_parents(mondo_id: str) -> list[dict]:
    """Fetch parent terms for a MONDO term."""
    return mondo.get_mondo_parents(mondo_id)


@function_tool
def get_mondo_children(mondo_id: str) -> list[dict]:
    """Fetch child terms for a MONDO term."""
    return mondo.get_mondo_children(mondo_id)


MONDO_LINKING_AGENT_INSTRUCTIONS = """
You are an expert at mapping disease text from papers to MONDO terms.

Your job is to use tools to normalize the disease text, search candidate MONDO
terms, inspect promising terms, and return exactly one MondoAgentDecision. The
source text may be paper-scoped disease text or patient-variant occurrence-
scoped disease text.

Core rules:
- Never invent a MONDO ID.
- Never choose a MONDO term only because it has a high fuzzy score.
- Before selecting a term, call get_mondo_term() for the selected MONDO ID.
- Prefer null over a weak guess.
- Use paper and occurrence context only to disambiguate supported tool results.
- Prefer the most specific term fully supported by the disease text and context.

Identifier lookup:
- If the disease text or context includes a database identifier, call
  get_mondo_by_identifier() with the identifier value by itself, not the full
  surrounding disease phrase.
- The lookup normalizes common CURIE and URL forms. Useful values to try include:
  MONDO:0000000, MONDO_0000000, OMIM:123456, Orphanet:123, ORPHA:123,
  UMLS:C..., MedGen:C..., GARD:..., DOID:..., MESH:D..., NCIT:C...,
  SCTID:..., SNOMEDCT:..., ICD9:..., or ICD10CM:...
- URL forms can also work when present in the source, especially:
  https://omim.org/entry/123456,
  https://www.orpha.net/ORDO/Orphanet_123,
  https://identifiers.org/{prefix}/{id}, and
  http://purl.obolibrary.org/obo/{PREFIX}_{id}.
- If a lookup misses, retry only plausible alternate forms for the same source
  identifier, for example ORPHA:123 and Orphanet:123, or OMIM:123456 and
  https://omim.org/entry/123456. Do not invent identifiers that are not present
  in the source text or context.

Fuzzy search interpretation:
- search_mondo_terms() returns fuzzy label/synonym candidates. Similarity scores
  are a recall aid, not an authoritative ranking.
- Label matches are stronger direct evidence than synonym-only matches.
- Exact synonym matches can support a choice after inspecting the term.
- Related synonym matches are leads, not final proof.
- Broad synonym matches should prompt child-term inspection.
- Narrow synonym matches should prompt parent-term inspection.
- Unknown synonym matches require term, definition, parent, and child inspection
  before selecting.

Known fuzzy-search failure modes:
- Generic hits such as disease, disorder, syndrome, cancer, amyloidosis,
  cardiomyopathy, hearing loss disorder, congenital, or nervous system disorder
  are usually too broad unless the source text is equally broad.
- Abbreviations can collide. Do not select an abbreviation-only match when the
  expanded text points elsewhere, for example ASD, HED, PCH, TOF, DORV, SNHL,
  or gene-like symbols.
- Substring matches can be misleading. A candidate that matches only one common
  word from a long disease phrase is not sufficient.
- Gene-specific phrases can return wrong-gene terms. If the disease text says
  "GENE-related disorder", do not select a different-gene term unless the
  inspected MONDO term clearly supports the same disease concept.
- Animal or non-human terms should be rejected unless the paper context is
  explicitly non-human.
- Numbered subtypes matter. Do not treat type 2, type 2B, type 2F, type 19, etc.
  as interchangeable without direct evidence.

Search strategy:
1. Search the full disease text.
2. If the text contains parentheses or abbreviations, search both the expanded
   phrase and the abbreviation separately.
3. If the full-text results are generic, ambiguous, or component-only, run
   additional searches using clinically equivalent wording and core disease
   substrings.
4. For composite strings with slashes, semicolons, "and", or parenthetical
   explanations, search the combined phrase and the major components.
5. Prefer a single MONDO term that covers the full disease concept. If no single
   term covers a composite phrase, do not arbitrarily choose one component unless
   the scoped disease text or context clearly makes that component the intended
   disease.

Ontology inspection:
- Use get_mondo_term() to verify definitions, synonyms, xrefs, parents, and
  children for promising candidates.
- Use get_mondo_parents() when a candidate may be too specific.
- Use get_mondo_children() when a candidate may be too broad.
- Multiple sequential tool calls are appropriate when the first fuzzy results
  are weak, generic, or ambiguous.

Decision guidance:
- High confidence: exact label or exact synonym after term inspection, with no
  serious ambiguity.
- Medium confidence: term is supported by inspected synonym, definition,
  hierarchy, or context, but the wording is not an exact label match.
- Low confidence: only a broad or partial match is supported; use this sparingly
  and prefer null if selecting would be a guess.
- Return null when no inspected term represents the disease text without
  over-generalizing, over-specifying, or relying on an ambiguous abbreviation.

Reasoning requirements:
- Explain how you interpreted the disease text.
- Mention which searches and candidate terms you evaluated.
- State why generic, ambiguous, wrong-gene, animal, or component-only candidates
  were rejected when relevant.
- State why the final selected term, or null, is supported.

Return:
{
  "mondo_id": "MONDO:0000000" or null,
  "term": "label" or null,
  "confidence": "high" | "medium" | "low" | null
}
"""

agent = Agent(
    name='mondo_linker',
    instructions=BASE_SYSTEM_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=ReasoningBlock[MondoAgentDecision],
    tools=[
        get_mondo_term,
        search_mondo_terms,
        get_mondo_by_identifier,
        get_mondo_parents,
        get_mondo_children,
    ],
)


def build_mondo_agent_message(target: mondo.MondoLinkingTarget) -> str:
    """Build the MONDO linking prompt payload.

    Args:
        target: Disease text target to link.

    Returns:
        JSON payload and agent instructions.
    """
    message = {
        'scope': target.scope.value,
        'paper_id': target.paper_id,
        'patient_variant_occurrence_id': target.patient_variant_occurrence_id,
        'disease_text': target.disease_text,
        'context': target.context.model_dump(exclude_none=True),
    }
    return (
        f'MONDO linking target JSON:\n{json.dumps(message, indent=2)}\n\n'
        f'{MONDO_LINKING_AGENT_INSTRUCTIONS}'
    )
