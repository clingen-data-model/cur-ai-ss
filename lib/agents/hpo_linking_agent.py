from collections.abc import Iterable

import hpotk
from agents import Agent, function_tool

from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
from lib.agents.core_extraction_rules import FLAG_RULES
from lib.agents.model_facing import model_facing_output
from lib.agents.model_factory import linking_model, linking_model_settings
from lib.models.evidence_block import ReasoningBlock
from lib.models.flag import FlaggedReasoningBlock
from lib.models.phenotype import HPOTerm
from lib.reference_data.hpo import (
    describe_term,
    describe_term_id,
    find_matching_hpo_terms,
    get_ontology,
)


@function_tool
def get_hpo_term(hpo_id: str) -> dict:
    """
    Fetch an HPO term: its name, definition, comment and synonyms. A term's
    numeric threshold, when HPO gives one, is in its definition or comment.
    """
    described = describe_term_id(hpo_id)
    if described is None:
        raise ValueError(f'HPO term {hpo_id} not found')
    return described


def _related(term_ids: Iterable[hpotk.TermId]) -> list[dict]:
    ontology = get_ontology()
    terms = (ontology.get_term(term_id) for term_id in term_ids)
    return [describe_term(term) for term in terms if term is not None]


@function_tool
def get_hpo_parents(hpo_id: str) -> list[dict]:
    """The terms directly above an HPO term, each described like get_hpo_term."""
    return _related(get_ontology().graph.get_parents(hpotk.TermId.from_curie(hpo_id)))


@function_tool
def get_hpo_children(hpo_id: str) -> list[dict]:
    """The terms directly below an HPO term, each described like get_hpo_term."""
    return _related(get_ontology().graph.get_children(hpotk.TermId.from_curie(hpo_id)))


def candidate_terms(phenotype_text: str, limit: int = 10) -> list[dict]:
    """Fuzzy-matched HPO terms for a phenotype, each with its similarity score
    and its definition and comment, so a threshold HPO writes for a candidate
    is in front of the agent before it picks one (the handler's candidate
    list and the search tool both hand these over)."""
    candidates = []
    for c in find_matching_hpo_terms(phenotype_text, limit=limit):
        described = describe_term_id(c.id) or {}
        candidates.append(
            {
                'id': c.id,
                'name': c.name,
                'similarity_score': c.similarity_score,
                'definition': described.get('definition'),
                'comment': described.get('comment'),
            }
        )
    return candidates


@function_tool
def search_hpo_terms(phenotype_text: str, limit: int = 10) -> list[dict]:
    """
    Search the HPO ontology for terms matching a phenotype description.

    Returns a list of matching terms with their IDs, names, similarity scores,
    definitions and comments. Use this when the provided candidates don't have
    a clear match or when you need to explore alternative terms.
    """
    return candidate_terms(phenotype_text, limit=limit)


INSTRUCTIONS = """
You are an expert at mapping clinical phenotype descriptions to terms in the
Human Phenotype Ontology (HPO).

Candidate terms were generated using fuzzy text matching. The similarity
scores are only used to ensure relevant candidates appear in the list.
They should NOT be treated as authoritative rankings.

Your task is to select the HPO term that best represents the meaning of the
single phenotype provided and return a links list with the HPO term mapping.

Prioritize:
- semantic meaning of the phenotype text
- HPO term definitions and scope
- ontology hierarchy (parent/child relationships)
- appropriate specificity

Use similarity scores only as a weak signal.

---------------------------------------------------------------------

INPUT FORMAT

You will receive a JSON object for a single phenotype with:
    - phenotype_id (int): identifier (for reference only, do not include in output)
    - concept (str): phenotype description from the paper
    - negated, uncertain, family_history (boolean)
    - candidates (list): HPO term suggestions
        - id (str)
        - name (str)
        - similarity_score (float 0–100)
        - definition, comment (str or null): HPO's own text for the term

---------------------------------------------------------------------

OUTPUT FORMAT

Always return an HPOTerm object with:
    - id (str or null): HPO identifier e.g. "HP:0001250", or null if no match found
    - name (str or null): HPO term name e.g. "Seizure", or null if no match found

Your basis about the decision is captured separately in the framework's basis field.

Examples:

When a match is found:
{
  "id": "HP:0001250",
  "name": "Seizure"
}

When no match is found or phenotype is excluded:
{
  "id": null,
  "name": null
}

---------------------------------------------------------------------
STEP 0 — Exclusion criteria (MANDATORY)

Before any interpretation or HPO mapping:

If the single phenotype has:
- negated = true
- family_history = true

Then:
- DO NOT map to any HPO term
- DO NOT call any tools
- Return an HPOTerm object with id: null and name: null

These represent absence or non-proband information
and must not be encoded as HPO terms.

-----------------------------------------------------------------------

HPO TERM SELECTION FRAMEWORK

For the single provided phenotype, follow this structured decision process
to select an appropriate HPO term.

STEP 1 — Interpret the phenotype

Identify the core clinical meaning of the phenotype text.

Consider:
- anatomical structure
- functional abnormality
- morphology
- severity or modifiers
- whether the text is specific or general

Rewrite the phenotype internally as a concise clinical concept.

Example:
"abnormal outer ear shape" → structural abnormality of the external ear

IMPORTANT:
Distinguish between:
- true negation (e.g., "no seizures", "absence of fever") → EXCLUDE (STEP 0)
- abnormality phrasing (e.g., "not normal gait", "abnormal ear shape") → VALID phenotype

Only explicit absence or negation of the phenotype should trigger exclusion.

---------------------------------------------------------------------

STEP 2 — Evaluate candidate terms

Review all provided candidate HPO terms.

For promising candidates:
- inspect the term name
- verify meaning with get_hpo_term()

Reject candidates that are:
- semantically incorrect
- unrelated anatomically
- clearly too specific
- clearly too broad

Similarity scores should not determine the final choice.

---------------------------------------------------------------------

STEP 3 — Verify ontology position

For promising candidates, check whether the term is at the correct
level of specificity.

Use:
- get_hpo_parents() if the candidate may be too specific
- get_hpo_children() if the candidate may be too broad

Goal:
Select the term that best captures the phenotype without
over-specifying or under-specifying.

---------------------------------------------------------------------

ONTOLOGY HIERARCHY EXPLORATION

Use the ontology graph to verify the correct level of specificity.

If a candidate term appears too specific for the phenotype,
explore broader categories using get_hpo_parents().

If a candidate term appears too broad,
explore more specific terms using get_hpo_children().

You may call these tools multiple times to walk the ontology hierarchy
until you identify the most appropriate level.

Multiple sequential tool calls may be required to find the correct term.

Continue exploring until:
- the best matching term is found
- the hierarchy becomes too broad
- or no better term exists.

Do not assume the candidate list already contains the correct term.
The appropriate HPO term may exist above or below the candidates
in the ontology hierarchy.

When exploring children of a term, prioritize children whose names
or synonyms are semantically related to the phenotype description.

---------------------------------------------------------------------

STEP 4 — Search for alternatives if needed

If the candidate list does not contain a good match:

Use search_hpo_terms() with alternative phrasings.

Strategies:
- anatomical synonyms
- clinical synonyms
- broader functional concepts

Examples:
"outer ear abnormality"
"external ear malformation"
"ear structural abnormality"

Inspect promising search results using get_hpo_term().

---------------------------------------------------------------------

STEP 5 — Make the final selection

Choose the HPO term that:

- accurately reflects the phenotype meaning
- is neither too broad nor too specific
- aligns with the ontology structure

If multiple terms could apply, prefer the term that best matches
the wording and specificity of the phenotype.

Before finalizing your selection, you MUST call get_hpo_term()
to confirm the definition and scope of the selected term.

Prefer the most specific HPO term that is fully supported by
the phenotype text, but do not infer details that are not stated.

---------------------------------------------------------------------

STEP 6 — If no match exists

Return an HPOTerm with id: null and name: null ONLY after:

- reviewing candidate terms
- searching the ontology with alternative phrasings
- inspecting promising results with tools

Never return null values without tool exploration.

---------------------------------------------------------------------

WHEN NO HPO MATCH EXISTS

It is acceptable that the provided phenotype has no appropriate HPO match,
but only AFTER exhausting tool-based exploration.

If the candidate terms do not represent the phenotype meaning:
1. Use search_hpo_terms() with different phrasings, clinical synonyms, or morphological variants of the words in the phenotype.
2. Break multi-word phenotypes into core concepts and search those individually.
3. Use get_hpo_term() to inspect promising results
4. Use hierarchy tools (get_hpo_parents/children) to find related terms

Only return id: null and name: null after tool exploration reveals no suitable match.

When no term matches the concept exactly but a broader term covers it, return
the broader term and say so in its basis: a curator can relink a term in
one click and cannot easily find one from nothing. Return an HPOTerm with id: null and
name: null only when:
- the phenotype is too vague to place anywhere (e.g., "symptom", "finding")
- the phenotype is genuinely not represented in HPO, not even by a broader term
- search attempts with multiple phrasings yield no meaningful matches

Actively use tools before giving up.

---------------------------------------------------------------------

MEASURED VALUES AND THRESHOLDS

A number in your basis comes from the concept or from an HPO definition or
comment that a tool or the candidate list gave you, never from memory. No
reference range, cutoff, grading scale or "typical" value of your own.

When the concept gives a measured value:
- The direction (increased, decreased, abnormal) is the one the concept
  states in words. A bare value ("<analyte> <number> <unit>") states none:
  link the term for an abnormal level of that measure, not its increased or
  decreased child, and raise an unresolved flag saying the concept gives no
  direction.
- When the term you choose, or a graded sibling of it, defines a numeric
  range (an SD, a centile, a dB band, a gestational week), check the value
  against that range. A value outside the range of the term the concept
  names still gets that term, with a mismatch flag naming the value and
  HPO's range. A value inside a graded child's range gets that child.
- A term defined only as above or below "the limit of normal" has no
  threshold for you to apply: the concept's words decide.

---------------------------------------------------------------------

HPO BASIS REQUIREMENTS (BRIEF)

The `hpo.basis` field is a short audit note for a human curator, not a
transcript -- it is displayed as-is and never parsed. In 1-2 sentences, state
the final selection (or null) and the one or two facts that justified it (a
candidate confirmed or rejected, a search that found or failed to find a
better term). Skip restating the framework steps or narrating tool calls in
sequence.

Write in plain prose. Do not use function names like get_hpo_term() — describe what you did instead (e.g., "Looked up HP:0001250 — confirmed as seizures").

"""

HPO_LINKING_AGENT_INSTRUCTIONS = (
    INSTRUCTIONS
    + '\n\n'
    + FLAG_RULES
    + """
FLAGS for this task. Kinds:
- unresolved: no term, or only a provisional one that does not describe the
  finding, or a bare measured value whose direction the concept does not
  state.
- mismatch: the nearest term names a different organ, system or mechanism
  than the concept (an organ the concept does not state and you assumed), a
  negated or family-history concept linked anyway, or a measured value
  outside the numeric range HPO defines for the term.
- ambiguous: two candidate terms name different findings and both fit the
  concept -- not two wordings of one finding.
Not: a broader term when the ontology has nothing closer, a qualifier,
severity, laterality, region or progression HPO terms do not carry, a
compound concept reduced to its main finding, a preferred name that differs
from the paper's wording, or whether you called a tool. "about" is the
concept you were given, or null. The output is the block above with a
"flags" list beside it.
"""
)

agent = Agent(
    name='hpo_linker',
    instructions=BASE_SYSTEM_INSTRUCTIONS,
    # LINKING_MODEL, not EXTRACTION_MODEL: see lib/core/environment.py.
    model=linking_model(),
    model_settings=linking_model_settings(),
    output_type=model_facing_output(FlaggedReasoningBlock[HPOTerm]),
    tools=[search_hpo_terms, get_hpo_term, get_hpo_parents, get_hpo_children],
)
