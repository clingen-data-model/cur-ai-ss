#!/usr/bin/env python3
"""Add the original reasoning to HPO links reused before it was carried.

A phenotype whose concept was linked before is given that link on the spot,
with reasoning that says so (``reused_hpo_link_reasoning``). Since 2026-11-11
that reasoning ends with the HPO agent's own reasoning for the link it copied;
links reused before then say only where it came from. This adds it to them.

The copied link is not recorded, and may since have been re-extracted away,
so the original is found the way the cache would find it: the agent's links
of the same concept (case- and whitespace-insensitive, never negated or
family history) to the same term, the most recently written winning. A link
reused from a curator's link is left as it is, as a fresh reuse would leave
it, and so is one whose term no agent link of that concept still carries.

Only rows without an original reasoning are touched, so it is safe to re-run.
``updated_at`` is kept, since the cache orders links by it.

Usage:
    uv run python -m lib.bin.backfill_reused_hpo_reasoning [--dry-run]
"""

import argparse
import logging

from sqlalchemy import update
from sqlalchemy.orm import Session

from lib.api.db import session_scope
from lib.core.logging import setup_logging
from lib.models import EditDB, HpoDB, PhenotypeDB
from lib.tasks.handlers import ORIGINAL_REASONING_LABEL, REUSED_HPO_LINK_PREFIX
from lib.tasks.hpo_link_cache import normalize_concept

setup_logging()
logger = logging.getLogger(__name__)

CURATED_REUSE = ' by a curator '


def backfill(session: Session) -> tuple[int, int]:
    """Fill what can be filled; (filled, left without an original)."""
    curated = {
        link_id
        for (link_id,) in session.query(EditDB.hpo_link_id).filter(
            EditDB.hpo_link_id.isnot(None), EditDB.field_name == 'hpo'
        )
    }
    rows = (
        session.query(HpoDB.id, HpoDB.hpo_id, HpoDB.reasoning, PhenotypeDB.concept)
        .join(PhenotypeDB, PhenotypeDB.id == HpoDB.phenotype_id)
        .filter(
            HpoDB.hpo_id.isnot(None),
            PhenotypeDB.negated.is_(False),
            PhenotypeDB.family_history.is_(False),
        )
        .order_by(HpoDB.updated_at, HpoDB.id)
        .all()
    )
    originals: dict[tuple[str, str], str] = {}
    for link_id, hpo_id, reasoning, concept in rows:
        if link_id in curated or reasoning.startswith(REUSED_HPO_LINK_PREFIX):
            continue
        originals[(normalize_concept(concept), hpo_id)] = reasoning.strip()

    filled = missing = 0
    for link_id, hpo_id, reasoning, concept in rows:
        if (
            not reasoning.startswith(REUSED_HPO_LINK_PREFIX)
            or ORIGINAL_REASONING_LABEL in reasoning
            or CURATED_REUSE in reasoning
        ):
            continue
        original = originals.get((normalize_concept(concept), hpo_id))
        if not original:
            missing += 1
            continue
        session.execute(
            update(HpoDB)
            .where(HpoDB.id == link_id)
            .values(
                reasoning=f'{reasoning} {ORIGINAL_REASONING_LABEL}{original}',
                updated_at=HpoDB.updated_at,
            )
        )
        filled += 1
    return filled, missing


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument(
        '--dry-run', action='store_true', help='count, and roll back the changes'
    )
    args = parser.parse_args()
    with session_scope() as session:
        filled, missing = backfill(session)
        logger.info(
            f'Added the original reasoning to {filled} reused HPO links; '
            f'{missing} have no agent link of their concept to that term left'
        )
        if args.dry_run:
            session.rollback()
            logger.info('Dry run: rolled back')


if __name__ == '__main__':
    main()
