import time
from collections import defaultdict, namedtuple
from pathlib import Path

import hpotk
import requests
from rapidfuzz import fuzz, process

from lib.core.environment import env

HpoCandidate = namedtuple('HpoCandidate', ['hpo_id', 'hpo_name', 'similarity_score'])

ONTOLOGY_ENDPOINT = 'https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download/hp.json'
MAX_AGE_S = 7 * 24 * 60 * 60  # 7 days


def ontology_path() -> Path:
    return env.reference_data_dir / 'hpo.json'


def download_ontology() -> Path:
    path = ontology_path()
    tmp_path = path.with_suffix('.tmp')
    path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(ONTOLOGY_ENDPOINT, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    tmp_path.replace(path)
    return path


def ensure_ontology() -> Path:
    path = ontology_path()
    if not path.exists():
        return download_ontology()
    age = time.time() - path.stat().st_mtime
    if age > MAX_AGE_S:
        return download_ontology()
    return path


def build_term_lookup() -> defaultdict[str, list[hpotk.model._term_id.DefaultTermId]]:
    hpo = hpotk.load_ontology(str(ensure_ontology()))
    term_lookup = defaultdict(list)
    for term in hpo.terms:
        term_lookup[term.name.lower()].append(term.identifier)
        if not term.synonyms:
            continue
        for syn in term.synonyms:
            term_lookup[syn.name.lower()].append(term.identifier)
    return term_lookup


def find_matching_hpo_terms(
    phenotype_text: str,
    term_lookup: defaultdict[str, list[hpotk.model._term_id.DefaultTermId]],
    limit: int = 5,
    score_cutoff: float = 20.0,
) -> list[HpoCandidate]:
    """
    Find matching HPO terms for a phenotype text using rapidfuzz similarity scoring.

    Args:
        phenotype_text: The phenotype description text to match.
        term_lookup: A dict mapping term names to HPO term IDs.
        limit: Max number of candidates to return (default 5).
        score_cutoff: Minimum similarity score (0-100) to include a match (default 20).

    Returns:
        List of dicts with keys:
            - hpo_id: The HPO ID string (e.g., "HP:0001234")
            - hpo_name: The official term name
            - similarity_score: Float between 0-100
    """
    all_terms = list(term_lookup.keys())
    top_matches = process.extract(
        phenotype_text.lower(),
        all_terms,
        # "This works best for ontology matching because it ignores extra words and focuses on shared tokens"
        # per ChatGPT: ontology terms are usually short canonical phrases
        # text often contains modifiers or extra context
        # order may vary
        # Algorithm:
        # Extract tokens
        # Compute:
        #    intersection tokens
        #    unique tokens in each string
        # Compare combinations of these token groups
        scorer=fuzz.token_set_ratio,
        limit=limit,
        score_cutoff=score_cutoff,
    )

    candidates: list[HpoCandidate] = []
    for name, score, _ in top_matches:
        hpo_ids = term_lookup[name]
        if hpo_ids:
            hpo_id = str(hpo_ids[0])
            candidate = HpoCandidate(
                hpo_id=hpo_id,
                hpo_name=name,
                similarity_score=float(score),
            )
            candidates.append(candidate)

    if not candidates:
        # fallback root phenotype
        candidates.append(
            HpoCandidate(
                hpo_id='HP:0000118',
                hpo_name='Phenotypic abnormality',
                similarity_score=0.0,
            )
        )
    return candidates
