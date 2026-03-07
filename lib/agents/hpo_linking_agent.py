import hpotk
from agents import Agent, function_tool

from lib.core.environment import env
from lib.models import PhenotypeLinkingOutput
from lib.reference_data.hpo import ensure_ontology

# Lazy-loaded ontology
_ontology: hpotk.MinimalOntology | None = None


def _get_ontology() -> hpotk.MinimalOntology:
    """Load and cache the HPO ontology."""
    global _ontology
    if _ontology is None:
        _ontology = hpotk.load_ontology(str(ensure_ontology()))
    return _ontology


@function_tool
def get_hpo_term(hpo_id: str) -> dict:
    """
    Fetch HPO term information.
    """
    ontology = _get_ontology()
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
    ontology = _get_ontology()
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
    ontology = _get_ontology()
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
    - negated, uncertain, family_history, notes (all boolean/string)
    - onset, location, severity, modifier, section (string or null)
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

3. Use ontology tools when helpful
   - get_hpo_term(hpo_id) to inspect term details
   - get_hpo_parents(hpo_id) to understand broader categories
   - get_hpo_children(hpo_id) to explore more specific terms

   This is useful when:
   - candidates have similar meanings
   - the phenotype appears more specific than the candidates
   - term definitions are needed for clarification

4. Select the best matching term
   Prefer terms that:
   - accurately represent the phenotype
   - have appropriate specificity
   - match the clinical meaning

---------------------------------------------------------------------

WHEN NO HPO MATCH EXISTS

It is acceptable that a phenotype has no appropriate HPO match.

If none of the candidate terms represent the phenotype meaning, leave:
- hpo_id: null
- hpo_name: null
- hpo_confidence: null

Use this when:
- the phenotype is too vague
- the phenotype is not represented in HPO
- no candidate meaningfully matches the phenotype
- selecting a term would require guessing

It is better to return null than to select an incorrect HPO term.

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
      "notes": "...",
      "onset": null,
      "location": null,
      "severity": null,
      "modifier": null,
      "section": null,
      "confidence": 0.95,
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
      "notes": "...",
      "onset": null,
      "location": null,
      "severity": null,
      "modifier": null,
      "section": null,
      "confidence": 0.85,
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
- Include all original phenotype fields (text, negated, uncertain, etc).
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
    tools=[get_hpo_term, get_hpo_parents, get_hpo_children],
)
