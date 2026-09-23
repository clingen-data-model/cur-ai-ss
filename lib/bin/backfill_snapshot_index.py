#!/usr/bin/env python3
"""Backfill the snapshots index table from existing on-disk snapshot files.

list_snapshots() now reads only the snapshots table (see lib/misc/snapshots.py)
instead of json.loads()-ing every on-disk snapshot file, so any snapshot
written before that table existed is invisible to the Restore Snapshot picker
until this runs. Reads each on-disk snapshot file's `meta` block once and
inserts one SnapshotDB row per file that doesn't already have one.

Safe to re-run: skips any file whose name already has a row.

Usage:
    uv run python -m lib.bin.backfill_snapshot_index
"""

import json
import logging
from datetime import datetime

from lib.api.db import session_scope
from lib.core.logging import setup_logging
from lib.misc.snapshots import snapshot_file_paths
from lib.models import PaperDB, SnapshotDB

setup_logging()
logger = logging.getLogger(__name__)


def backfill() -> None:
    with session_scope() as session:
        paper_ids = [i for (i,) in session.query(PaperDB.id).order_by(PaperDB.id)]

    inserted = 0
    skipped = 0
    failed = 0
    for paper_id in paper_ids:
        paths = snapshot_file_paths(paper_id)
        if not paths:
            continue
        # One session per paper so a single bad file doesn't roll back the rest.
        with session_scope() as session:
            existing_names = {
                name
                for (name,) in session.query(SnapshotDB.name).filter(
                    SnapshotDB.paper_id == paper_id
                )
            }
            for path in paths:
                if path.name in existing_names:
                    skipped += 1
                    continue
                try:
                    meta = json.loads(path.read_text())['meta']
                    session.add(
                        SnapshotDB(
                            paper_id=paper_id,
                            name=path.name,
                            version=meta['version'],
                            created_at=datetime.fromisoformat(meta['created_at']),
                            alembic_revision=meta.get('alembic_revision'),
                            model=meta.get('model'),
                            description=meta.get('description'),
                            git_hash=meta.get('git_hash'),
                            state_hash=meta['state_hash'],
                        )
                    )
                    inserted += 1
                except (OSError, ValueError, KeyError):
                    logger.exception(
                        f'Paper {paper_id}: unreadable snapshot {path.name}'
                    )
                    failed += 1

    logger.info(
        f'Done: {inserted} inserted, {skipped} already indexed, {failed} failed'
    )


if __name__ == '__main__':
    backfill()
