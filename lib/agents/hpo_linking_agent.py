import hpotk
from agents import Agent, function_tool

from lib.core.environment import env
from lib.models import PhenotypeLinkingOutput
from lib.reference_data.hpo import find_matching_hpo_terms, get_ontology


@function_tool
def get_hpo_term(hpo_id: str) -> dict:
    """
    Fetch HPO term information.
    """
    ontology = get_ontology()
    term_id = hpotk.TermId.from_curie(hpo_id)
    term = ontology.get_term(term_id)

    if not term:
        raise ValueError(f'HPO term {hpo_id} not found')

    return {
        'id': str(term.identifier.value),
        'name': term.name,
        'definition': term.definition,
        'synonyms': [s.name for s in term.synonyms],
    }


@function_tool
def get_hpo_parents(hpo_id: str) -> list[dict]:
    ontology = get_ontology()
    term_id = hpotk.TermId.from_curie(hpo_id)

    parents = []
    for pid in ontology.graph.get_parents(term_id):
        term = ontology.get_term(pid)
        if term:
            parents.append(
                {
                    'id': str(term.identifier.value),
                    'name': term.name,
                    'definition': term.definition,
                    'synonyms': [s.name for s in term.synonyms],
                }
            )

    return parents


@function_tool
def get_hpo_children(hpo_id: str) -> list[dict]:
    ontology = get_ontology()
    term_id = hpotk.TermId.from_curie(hpo_id)

    children = []
    for cid in ontology.graph.get_children(term_id):
        term = ontology.get_term(cid)
        if term:
            children.append(
                {
                    'id': str(term.identifier.value),
                    'name': term.name,
                    'definition': term.definition,
                    'synonyms': [s.name for s in term.synonyms],
                }
            )

    return children


@function_tool
def search_hpo_terms(phenotype_text: str, limit: int = 10) -> list[dict]:
    """
    Search the HPO ontology for terms matching a phenotype description.

    Returns a list of matching terms with their IDs, names, and similarity scores.
    Use this when the provided candidates don't have a clear match or when you need
    to explore alternative terms.
    """
    candidates = find_matching_hpo_terms(phenotype_text, limit=limit)
    return [
        {
            'hpo_id': c.hpo_id,
            'hpo_name': c.hpo_name,
            'similarity_score': c.similarity_score,
        }
        for c in candidates
    ]


INSTRUCTIONS = """
You are an expert at mapping clinical phenotype descriptions to terms in the
Human Phenotype Ontology (HPO).

Candidate terms were generated using fuzzy text matching. The similarity
scores are only used to ensure relevant candidates appear in the list.
They should NOT be treated as authoritative rankings.

Your task is to select the HPO term that best represents the meaning of each
phenotype description and return the enriched phenotype data with HPO links.

Prioritize:
- semantic meaning of the phenotype text
- HPO term definitions and scope
- ontology hierarchy (parent/child relationships)
- appropriate specificity

Use similarity scores only as a weak signal.

---------------------------------------------------------------------

INPUT FORMAT

You will receive a JSON object with:

- phenotypes: array of phenotype entries containing:
    - patient_id (int)
    - text (str): phenotype description from the paper
    - negated, uncertain, family_history (boolean)
    - confidence (float): extraction confidence
    - candidates (list): HPO term suggestions
        - hpo_id (str)
        - hpo_name (str)
        - similarity_score (float 0–100)

---------------------------------------------------------------------

HPO TERM SELECTION FRAMEWORK

For each phenotype, follow this structured decision process before
selecting an HPO term.

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

Before assigning **high confidence**, you MUST call get_hpo_term()
to confirm the definition and scope of the selected term.

Prefer the most specific HPO term that is fully supported by
the phenotype text, but do not infer details that are not stated.

---------------------------------------------------------------------

STEP 6 — If no match exists

Return null ONLY after:

- reviewing candidate terms
- searching the ontology with alternative phrasings
- inspecting promising results with tools

Never return null without tool exploration.

---------------------------------------------------------------------

WHEN NO HPO MATCH EXISTS

It is acceptable that a phenotype has no appropriate HPO match, but only AFTER
exhausting tool-based exploration.

If none of the candidate terms represent the phenotype meaning:
1. Use search_hpo_terms() with different phrasings or clinical synonyms
2. Use get_hpo_term() to inspect promising results
3. Use hierarchy tools (get_hpo_parents/children) to find related terms

Only return null after tool exploration reveals no suitable match:
- hpo_id: null
- hpo_name: null
- hpo_confidence: null

Return null when:
- the phenotype is too vague (e.g., "symptom", "finding")
- the phenotype is genuinely not represented in HPO
- search attempts with multiple phrasings yield no meaningful matches
- selecting any term would require significant guessing

It is better to return null than to select an incorrect HPO term, but
actively use tools before giving up.

---------------------------------------------------------------------

CONFIDENCE LEVELS

Only assign hpo_confidence when an HPO term is selected.

high
    Clear semantic match between phenotype and HPO term.

moderate
    Reasonable match with some ambiguity or minor mismatch
    in specificity.

low
    Approximate match but still clinically related.

If no HPO term is selected, hpo_confidence must be null.

---------------------------------------------------------------------

HPO_MATCH_NOTES REQUIREMENTS (STEP-BY-STEP JUSTIFICATION)

The `hpo_match_notes` field MUST summarize the reasoning process
using the HPO TERM SELECTION FRAMEWORK.

The explanation should document the resolution process in a concise
step-by-step format.

Include:

1. Phenotype interpretation
2. Candidate evaluation
3. Tool usage
4. Hierarchy reasoning
5. Final selection

Do not omit tool calls if they were used.

---------------------------------------------------------------------

OUTPUT FORMAT
...
"""

agent = Agent(
    name='hpo_linker',
    instructions=INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=PhenotypeLinkingOutput,
    tools=[search_hpo_terms, get_hpo_term, get_hpo_parents, get_hpo_children],
)
