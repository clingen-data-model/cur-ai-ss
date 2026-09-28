"""Exact-match cache of phenotype concept -> HPO term, for HPO_LINKING.

The same concept text ("seizures", "intellectual disability") recurs across
patients and papers, and each occurrence used to cost a full agent walk of the
ontology to land on the same term again. This holds every existing non-null
link in memory, keyed by the normalized concept, so handle_phenotype_extraction
can link a repeat concept on the spot -- no HPO_LINKING task, no agent run.

A plain dict per worker process is enough at the sizes involved -- one entry
per distinct concept, a few hundred bytes each. The worker records its own new
links as it makes them, but a curator's relink happens in the API process, so
the dict is also rebuilt from the database every RELOAD_INTERVAL_S to pick
those up.

Only negated/family-history-free phenotypes are cached or served: the agent is
instructed to return no term for those regardless of the concept text.
"""

import logging
import time
from typing import NamedTuple

from sqlalchemy.orm import Session

from lib.api.db import session_scope
from lib.models import EditDB, HpoDB, PhenotypeDB

logger = logging.getLogger(__name__)

# Past this the dict is still correct, just worth reconsidering (an indexed
# lookup against the hpos table, say) -- so warn rather than cap.
EXPECTED_MAX_ENTRIES = 100_000

# How stale a curator's relink can be before new phenotypes see it. A reload is
# one query over the hpos table, so this can be short.
RELOAD_INTERVAL_S = 300


class CachedHpoLink(NamedTuple):
    hpo_id: str
    hpo_name: str
    # The phenotype whose link this came from, cited in the reused reasoning.
    source_phenotype_id: int
    # Set by a curator (it has an 'hpo' edit row) rather than by the agent.
    # A curated entry is never replaced by an agent-derived one.
    curated: bool


_cache: dict[str, CachedHpoLink] | None = None
_loaded_at = 0.0


def normalize_concept(concept: str) -> str:
    """Case- and whitespace-insensitive key: "Short  Stature" == "short stature"."""
    return ' '.join(concept.casefold().split())


def is_cacheable(phenotype: PhenotypeDB) -> bool:
    return not phenotype.negated and not phenotype.family_history


def _put(cache: dict[str, CachedHpoLink], concept: str, link: CachedHpoLink) -> None:
    key = normalize_concept(concept)
    existing = cache.get(key)
    if existing is not None and existing.curated and not link.curated:
        return
    cache[key] = link


def load_hpo_link_cache(session: Session) -> dict[str, CachedHpoLink]:
    """Build the cache from the hpos table. When several phenotypes share a
    concept, a curated link beats an agent one, and otherwise the most
    recently written link wins."""
    curated_link_ids = {
        link_id
        for (link_id,) in session.query(EditDB.hpo_link_id)
        .filter(EditDB.hpo_link_id.isnot(None), EditDB.field_name == 'hpo')
        .distinct()
    }
    rows = (
        session.query(
            HpoDB.id,
            HpoDB.hpo_id,
            HpoDB.hpo_name,
            HpoDB.phenotype_id,
            PhenotypeDB.concept,
        )
        .join(PhenotypeDB, PhenotypeDB.id == HpoDB.phenotype_id)
        .filter(
            HpoDB.hpo_id.isnot(None),
            HpoDB.hpo_name.isnot(None),
            PhenotypeDB.negated.is_(False),
            PhenotypeDB.family_history.is_(False),
        )
        .order_by(HpoDB.updated_at, HpoDB.id)
    )
    cache: dict[str, CachedHpoLink] = {}
    for link_id, hpo_id, hpo_name, phenotype_id, concept in rows:
        _put(
            cache,
            concept,
            CachedHpoLink(hpo_id, hpo_name, phenotype_id, link_id in curated_link_ids),
        )
    return cache


def get_hpo_link_cache() -> dict[str, CachedHpoLink]:
    """The process-wide cache, loaded on first use and reloaded once it is
    more than RELOAD_INTERVAL_S old."""
    global _cache, _loaded_at
    if _cache is None or time.monotonic() - _loaded_at > RELOAD_INTERVAL_S:
        with session_scope() as session:
            _cache = load_hpo_link_cache(session)
        _loaded_at = time.monotonic()
        logger.info(f'Loaded {len(_cache)} cached HPO links')
        if len(_cache) > EXPECTED_MAX_ENTRIES:
            logger.warning(
                f'HPO link cache has {len(_cache)} entries, past the '
                f'{EXPECTED_MAX_ENTRIES} it was sized for'
            )
    return _cache


def lookup_hpo_link(concept: str) -> CachedHpoLink | None:
    return get_hpo_link_cache().get(normalize_concept(concept))


def remember_hpo_link(
    concept: str, hpo_id: str, hpo_name: str, phenotype_id: int
) -> None:
    """Record a link the agent just produced."""
    _put(
        get_hpo_link_cache(),
        concept,
        CachedHpoLink(hpo_id, hpo_name, phenotype_id, curated=False),
    )


def reset_hpo_link_cache() -> None:
    """Drop the cache so the next use reloads it (tests)."""
    global _cache
    _cache = None
