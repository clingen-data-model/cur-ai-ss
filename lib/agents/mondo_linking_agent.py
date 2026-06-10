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

Your job is to use tools to normalize the disease text, try candidate searches,
inspect terms, and return exactly one MondoAgentDecision. The source text may be
paper-scoped disease text or patient-variant occurrence-scoped disease text.

Rules:
- Never invent a MONDO ID.
- If the disease text or context includes any identifier such as a MONDO ID,
  MONDO OBO IRI, OMIM, Orphanet, GARD, MedGen, MeSH, DOID, ICD, or UMLS, call
  get_mondo_by_identifier(). If an identifier lookup misses, retry alternate
  namespace formats for the same identifier, (e.g. Orphanet:123, ORPHA:123).
- For free text, call search_mondo_terms() with useful disease substrings,
  abbreviations, and clinically equivalent wording.
- Search results are candidate terms with match evidence rows. Label matches are
  stronger direct evidence than synonym-only matches. Exact synonym matches can
  support a choice after inspecting the term. Related synonym matches are leads,
  not final proof.
- Broad synonym matches should prompt child-term inspection. Narrow synonym
  matches should prompt parent-term inspection. Unknown synonym matches require
  term, definition, parent, and child inspection before selecting.
- Before selecting a term, call get_mondo_term() for the selected MONDO ID.
- Use the parents and children returned by get_mondo_term(), or call
  get_mondo_parents() / get_mondo_children() for deeper traversal, when
  specificity is unclear.
- Prefer null over a weak guess.
- Use paper and occurrence context only to disambiguate supported tool results.
- Prefer the most specific term supported by the input disease text and context.

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
