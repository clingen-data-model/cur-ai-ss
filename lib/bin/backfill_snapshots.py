#!/usr/bin/env python3
"""Write an extraction snapshot for every paper in the database (one-off seed).

Papers extracted before the snapshot feature shipped have no restore point, so
the Reset button is disabled for them. This writes one snapshot per paper from
its *current* database state.

Caveat: for papers that have already been hand-edited, the snapshot captures
those edits — the pre-edit state is unrecoverable. The snapshot still serves as
a restore point for everything that happens after this script runs.

Safe to re-run: write_snapshot dedupes on a state hash, so a paper whose state
is unchanged since its latest snapshot is skipped.

Usage:
    uv run python -m lib.bin.backfill_snapshots
"""

import logging

from lib.api.db import session_scope
from lib.core.logging import setup_logging
from lib.misc.snapshots import write_snapshot
from lib.models import PaperDB

setup_logging()
logger = logging.getLogger(__name__)


def backfill() -> None:
    with session_scope() as session:
        paper_ids = [i for (i,) in session.query(PaperDB.id).order_by(PaperDB.id)]

    written = 0
    skipped = 0
    failed = 0
    for paper_id in paper_ids:
        # One session per paper so a single failure doesn't roll back the rest.
        try:
            with session_scope() as session:
                path = write_snapshot(
                    paper_id, session, description='Manual snapshot backfill'
                )
        except Exception:
            logger.exception(f'Paper {paper_id}: snapshot failed')
            failed += 1
            continue
        if path is None:
            logger.info(f'Paper {paper_id}: unchanged since latest snapshot, skipped')
            skipped += 1
        else:
            logger.info(f'Paper {paper_id}: wrote {path.name}')
            written += 1

    logger.info(
        f'Done: {written} written, {skipped} skipped, {failed} failed '
        f'({len(paper_ids)} papers total)'
    )


if __name__ == '__main__':
    backfill()
