import time
from collections import defaultdict, namedtuple
from pathlib import Path

import hpotk
import requests
from rapidfuzz import fuzz, process

from lib.core.environment import env
from lib.models import HpoCandidate

# Lazy-loaded ontology
_ontology: hpotk.MinimalOntology | None = None
# Lazy-loaded name/synonym -> HPO id lookup, built from the ontology above
_term_lookup: defaultdict[str, list[hpotk.model._term_id.DefaultTermId]] | None = None

MAX_AGE_S = 7 * 24 * 60 * 60  # 7 days


def ontology_path() -> Path:
    return env.reference_data_dir / 'hpo.json'


def ontology_url() -> str:
    """Return the configured HPO ontology download URL."""
    return env.HPO_ONTOLOGY_URL


def download_ontology() -> Path:
    path = ontology_path()
    tmp_path = path.with_suffix('.tmp')
    path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(ontology_url(), stream=True, timeout=60) as r:
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


def get_ontology() -> hpotk.MinimalOntology:
    """Load and cache the HPO ontology."""
    global _ontology
    if _ontology is None:
        _ontology = hpotk.load_ontology(str(ensure_ontology()))
    return _ontology


def build_term_lookup() -> defaultdict[str, list[hpotk.model._term_id.DefaultTermId]]:
    """Build the name/synonym -> HPO id lookup fresh from the ontology.

    Iterates every one of the ~19,000 HPO terms plus their synonyms, so this
    is the expensive step -- callers wanting the normal cached behavior
    should use get_term_lookup() instead. Kept as its own function for
    callers that genuinely want a fresh build (there are none in this repo
    today; it exists mainly so get_term_lookup() has something to wrap and
    tests can exercise the two steps separately)."""
    hpo = get_ontology()
    term_lookup = defaultdict(list)
    for term in hpo.terms:
        term_lookup[term.name.lower()].append(term.identifier)
        if not term.synonyms:
            continue
        for syn in term.synonyms:
            term_lookup[syn.name.lower()].append(term.identifier)
    return term_lookup


def get_term_lookup() -> defaultdict[str, list[hpotk.model._term_id.DefaultTermId]]:
    """Build and cache the term lookup, same lifetime as get_ontology()'s cache.

    Before this existed, every call to find_matching_hpo_terms() with no
    term_lookup passed in -- every /hpo/search request from the UI combobox,
    and every search_hpo_terms tool call the HPO linking agent's tool loop
    makes -- rebuilt this from scratch: a full pass over every HPO term and
    synonym. That is the dominant cost in a search request (the ontology
    object itself was already cached), and it ran on every keystroke-driven
    search, not just the first one per process."""
    global _term_lookup
    if _term_lookup is None:
        _term_lookup = build_term_lookup()
    return _term_lookup


def warm_term_lookup_if_cached() -> None:
    """Eagerly build the term lookup at process startup, but only when the
    ontology is already cached on disk.

    Called from both the API's lifespan() and the worker's module-level
    startup, so the first real /hpo/search request or search_hpo_terms tool
    call doesn't pay for building the ~19k-term lookup. Skipped when the
    ontology file isn't on disk yet (a cold CAA_ROOT -- every test run
    against .env.test, or a brand-new deployment) so that warming never turns
    into an eager network download at startup; get_term_lookup() already
    falls back to building lazily on first use in that case, same as before
    this existed.
    """
    if not ontology_path().exists():
        return
    get_term_lookup()


def find_matching_hpo_terms(
    phenotype_text: str,
    limit: int = 10,
    score_cutoff: float = 20.0,
    term_lookup: defaultdict[str, list[hpotk.model._term_id.DefaultTermId]]
    | None = None,
) -> list[HpoCandidate]:
    """
    Match free-text phenotype descriptions to candidate HPO terms using fuzzy matching.

    Strategy
    --------
    1. Use RapidFuzz `token_sort_ratio` to compare the query against all HPO names and
       synonyms. This scorer ignores word order but penalizes extra tokens, which helps
       rank more specific ontology terms lower when the query is generic.

    2. Retrieve a moderately large pool of matches (e.g. 10 x expected_output) to ensure good recall.

    3. Collapse synonyms by HPO ID, keeping only the best-scoring string for each term.

    4. Sort candidates by similarity score and return the top `limit`.

    If no candidates pass the cutoff, the root phenotype term
    ("Phenotypic abnormality", HP:0000118) is returned as a fallback.

    BPB Note: token_sort_order > token_set_order to improve performace of short queries
    matching too many queries.
    """
    if not term_lookup:
        term_lookup = get_term_lookup()

    query = phenotype_text.lower()
    all_terms = list(term_lookup.keys())

    matches = process.extract(
        query,
        all_terms,
        scorer=fuzz.token_sort_ratio,
        limit=10 * limit,
        score_cutoff=score_cutoff,
    )

    best_by_hpo: dict[str, HpoCandidate] = {}

    for name, score, _ in matches:
        hpo_id = str(term_lookup[name][0])

        candidate = HpoCandidate(
            id=hpo_id,
            name=name,
            similarity_score=float(score),
        )

        if hpo_id not in best_by_hpo or score > best_by_hpo[hpo_id].similarity_score:
            best_by_hpo[hpo_id] = candidate

    candidates = sorted(
        best_by_hpo.values(),
        key=lambda c: c.similarity_score,
        reverse=True,
    )[:limit]

    if not candidates:
        candidates.append(
            HpoCandidate(
                id='HP:0000118',
                name='Phenotypic abnormality',
                similarity_score=0.0,
            )
        )

    return candidates
