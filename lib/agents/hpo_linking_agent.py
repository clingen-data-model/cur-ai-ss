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
        'id': str(term.id),
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
                    'id': str(term.id),
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
                    'id': str(term.id),
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

TASK

For each phenotype:

1. Understand the phenotype
   Identify the core clinical concept. Ignore stylistic differences
   or wording variations.

2. Review candidate terms
   Do not assume the top candidate is correct. Evaluate multiple
   candidates for semantic accuracy.

3. Use tools actively when there is NO clear match
   If none of the provided candidates seem like a good fit, you MUST use tools
   to explore further. Do not return null prematurely.

   Available tools:
   - search_hpo_terms(phenotype_text) - Search the ontology with alternative
     phrasings or synonyms. Use this when provided candidates are poor matches.
   - get_hpo_term(hpo_id) - Inspect details, definition, and synonyms of a term
   - get_hpo_parents(hpo_id) - Understand broader categories
   - get_hpo_children(hpo_id) - Explore more specific terms

   Strategy for unclear phenotypes:
   - Try rephrasing the phenotype using clinical synonyms
   - Search for related anatomical terms or functional concepts
   - Use get_hpo_term() to read definitions of search results
   - Use get_hpo_parents() if a term seems too specific
   - Use get_hpo_children() if a term seems too broad

4. Select the best matching term
   Prefer terms that:
   - accurately represent the phenotype
   - have appropriate specificity
   - match the clinical meaning

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

OUTPUT FORMAT

Return a JSON object with the enriched phenotype data:

{
  "phenotypes": [
    {
      "patient_id": 1,
      "text": "seizures",
      "negated": false,
      "uncertain": false,
      "family_history": false,
      "confidence": 0.95,
      "candidates": [...],
      "hpo_id": "HP:0001250",
      "hpo_name": "Seizure",
      "hpo_confidence": "high",
      "hpo_match_notes": "The phenotype explicitly describes seizures."
    },
    {
      "patient_id": 1,
      "text": "...",
      "negated": false,
      "uncertain": false,
      "family_history": false,
      "confidence": 0.85,
      "candidates": [...],
      "hpo_id": null,
      "hpo_name": null,
      "hpo_confidence": null,
      "hpo_match_notes": "Phenotype description is too vague to map to a specific HPO term."
    }
  ]
}

---------------------------------------------------------------------

IMPORTANT NOTES

- Maintain the same order as the input.
- Return exactly one enriched phenotype per input phenotype.
- Include all input phenotype fields (patient_id, text, negated, uncertain, family_history, confidence, candidates).
- If no HPO match exists, set hpo_id, hpo_name, and hpo_confidence to null.
- Duplicate HPO terms per patient are allowed.
- Only use HPO IDs from the candidate list or ontology tools.
- Do not rely solely on similarity_score.
"""

agent = Agent(
    name='hpo_linker',
    instructions=INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=PhenotypeLinkingOutput,
    tools=[search_hpo_terms, get_hpo_term, get_hpo_parents, get_hpo_children],
)
