"""Tool-using agent for MONDO disease linking."""

from agents import Agent, function_tool

from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
from lib.agents.hpo_linking_agent import (
    get_hpo_children,
    get_hpo_parents,
    get_hpo_term,
    search_hpo_terms,
)
from lib.core.environment import env
from lib.models.evidence_block import ReasoningBlock
from lib.models.mondo import MondoAgentDecision
from lib.reference_data import mondo


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

Your job is to use tools to normalize disease text. The source text may be
paper-scoped disease text or patient-variant occurrence-scoped disease text.

You must first try to map the full disease_text to one MONDO term. Only if no
MONDO term appropriately represents the full disease_text should you decompose
the input into components and map those components.

Core rules:
- Never invent a MONDO ID.
- Never invent an HPO ID.
- Never choose a MONDO term only because it has a high fuzzy score.
- Before selecting a term, call get_mondo_term() for the selected MONDO ID.
- Before selecting an HPO component mapping, call get_hpo_term() for the HPO ID.
- Prefer null over a weak guess.
- Use paper and occurrence context only to disambiguate supported tool results.
- Prefer the most specific term fully supported by the disease text and context.
- Component mappings are supporting normalization details. They are not the same
  as selecting multiple paper-level MONDO terms.
- The top-level mondo_id is the only selected primary MONDO term.

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

FULL-STRING MONDO STRATEGY

1. Search the full disease text.
2. If the text contains parentheses or abbreviations, search both the expanded
   phrase and the abbreviation separately.
3. If the full-text results are generic, ambiguous, or component-only, run
   additional searches using clinically equivalent wording and core disease
   substrings.
4. Prefer a single MONDO term that covers the full disease concept.

If you find a MONDO term that appropriately represents the full disease_text,
return match_type "exact" or "broad" and leave components empty.

- Use "exact" when the selected MONDO term captures the full disease_text at the
  same specificity.
- Use "broad" when the selected MONDO term acceptably represents the full
  disease concept but is broader than the source wording.

Do not decompose when a full-string MONDO match is appropriate, even if the
source text itself has multiple clear factors.

FALLBACK DECOMPOSITION STRATEGY

Only use this section when no appropriate full-string MONDO match exists.

1. Decompose the original disease_text into clinically meaningful components.
2. The components must account for the whole disease_text. Do not silently drop
   parenthetical modifiers, "and" clauses, secondary disease axes, or severity
   modifiers.
3. Mark at most one component as role "primary". Only do this when the text and
   context clearly support one component as the intended paper-level disease
   axis.
4. Mark remaining components as role "component" or "modifier".
5. Classify each component as category "disease", "phenotype", "mixed", or
   "unknown".
6. Try MONDO tools for disease-like and mixed components.
7. Try HPO tools for phenotype-like and mixed components.
8. Every component must have mapping_status "mapped", "unmapped", or "excluded".
9. If a primary component has an acceptable MONDO mapping and should be promoted
   as the selected paper-level MONDO term, return match_type "primary_partial"
   and set top-level mondo_id, term, and confidence.
10. If no component should be promoted as the selected paper-level MONDO term,
    return match_type "component_only" when at least one component maps to MONDO
    or HPO.
11. Return match_type "none" only when no full-string MONDO match exists and no
    useful component mappings exist.

For mapped components:
- mapped_ontology must be "MONDO" or "HPO".
- For MONDO mappings, populate mondo and leave hpo null.
- For HPO mappings, populate hpo and leave mondo null.
- relationship should describe the component match: "exact", "broad",
  "narrow", "related", or "partial".

For unmapped or excluded components:
- mapped_ontology, mondo, hpo, confidence, and relationship should be null.
- reasoning must explain why no mapping was selected.

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
- For component fallback, top-level mondo_id may be null even when component
  mappings exist.

Reasoning requirements:
- Explain how you interpreted the disease text.
- Mention which searches and candidate terms you evaluated (e.g., "Searched for 'dilated cardiomyopathy', top result was MONDO:0005021").
- State why generic, ambiguous, wrong-gene, animal, or component-only candidates
  were rejected when relevant.
- State why the final selected term, or null, is supported.
- If using fallback decomposition, explicitly explain why full-string MONDO
  matching failed, why each component string was chosen, which component is
  primary if any, and which components were mapped or unmapped.
- Write in plain prose. Do not use function names like get_mondo_term() — describe
  what you did instead (e.g., "Looked up MONDO:0005021 — confirmed label and definition match").

Return:
{
  "match_type": "exact" | "broad" | "primary_partial" | "component_only" | "none",
  "mondo_id": "MONDO:0000000" or null,
  "term": "label" or null,
  "confidence": "high" | "medium" | "low" | null,
  "components": []
}

When match_type is "exact" or "broad", components must be empty.
When match_type is "primary_partial", components must include one component with
role "primary" and a MONDO mapping matching the top-level selected MONDO term.
When match_type is "component_only", top-level mondo_id and term must be null.
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
        search_hpo_terms,
        get_hpo_term,
        get_hpo_parents,
        get_hpo_children,
    ],
)
