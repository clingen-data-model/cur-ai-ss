#!/usr/bin/env python3
"""Re-queue variant annotation (enrichment) for every harmonized variant.

Written to backfill VEP transcript consequence (added in b7e4a1f92c3d /
lib/agents/variant_annotation_agent.py's ``vep_lookup``) onto variants
annotated before that field existed. Unlike gnomAD allele counts
(backfill_gnomad_allele_counts.py), the consequence can only be produced by
re-running enrichment itself, not a targeted raw-API patch, since
``enrich_variants_batch`` is where it is computed.

Re-queues through ``enqueue_task`` -- the same path the "Rerun Agents" UI
button uses -- rather than inserting TaskDB rows directly, so idempotency,
status-reset and lease semantics match a normal manual rerun.
``skip_successors=True`` because VARIANT_ANNOTATION has no successors in
TASK_SUCCESSORS anyway; kept explicit for clarity.

Queues in batches of ``--batch-size`` (default 20) and waits for every task
in a batch to leave an ACTIVE status (Pending/Queued/Running) before queuing
the next, so at most one batch's worth of enrichment calls (VEP/gnomAD/
ClinVar lookups) are ever in flight against upstream APIs. The worker's own
``TASK_CONCURRENCY[VARIANT_ANNOTATION] = 10`` still governs how many of a
batch actually run at once -- this only bounds how many sit queued waiting
for a worker slot.

Requires the worker (``./bin/worker`` locally, or the ``worker`` systemd
user unit on dev-caa) to already be running -- this script only enqueues
tasks, it does not process them.

Usage:
    uv run python -m lib.bin.requeue_variant_annotation [--dry-run] [--batch-size N] [--poll-interval SECONDS]
"""

import argparse
import sys
import time

from lib.api.db import session_scope
from lib.models.variant import HarmonizedVariantDB, VariantDB, is_harmonized
from lib.tasks.misc import enqueue_task
from lib.tasks.models import ACTIVE_STATUSES, TaskDB, TaskType

DEFAULT_BATCH_SIZE = 20
DEFAULT_POLL_INTERVAL_SECONDS = 5.0


def _find_targets() -> list[tuple[int, int]]:
    """Return (paper_id, variant_id) for every successfully harmonized variant."""
    with session_scope() as session:
        rows = (
            session.query(HarmonizedVariantDB, VariantDB.paper_id)
            .join(VariantDB, HarmonizedVariantDB.variant_id == VariantDB.id)
            .order_by(VariantDB.id)
            .all()
        )
        return [(paper_id, hv.variant_id) for hv, paper_id in rows if is_harmonized(hv)]


def _queue_batch(targets: list[tuple[int, int]]) -> list[int]:
    task_ids = []
    with session_scope() as session:
        for paper_id, variant_id in targets:
            task = enqueue_task(
                session,
                paper_id=paper_id,
                task_type=TaskType.VARIANT_ANNOTATION,
                variant_id=variant_id,
                skip_successors=True,
                updated_by_user_id=None,
            )
            task_ids.append(task.id)
    return task_ids


def _wait_for_batch(task_ids: list[int], poll_interval: float) -> None:
    while True:
        with session_scope() as session:
            active = (
                session.query(TaskDB)
                .filter(TaskDB.id.in_(task_ids))
                .filter(TaskDB.status.in_(ACTIVE_STATUSES))
                .count()
            )
        if active == 0:
            return
        print(f'    waiting on {active}/{len(task_ids)} still active...')
        time.sleep(poll_interval)


def requeue(
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> None:
    targets = _find_targets()
    if not targets:
        print('Nothing to re-queue.')
        return

    print(
        f'Re-queuing variant annotation for {len(targets)} harmonized variants, '
        f'{batch_size} at a time.'
    )
    if dry_run:
        print('Dry run: no tasks queued.')
        return

    total_batches = (len(targets) + batch_size - 1) // batch_size
    for batch_num, start in enumerate(range(0, len(targets), batch_size), start=1):
        batch = targets[start : start + batch_size]
        print(
            f'Batch {batch_num}/{total_batches}: queuing {len(batch)} tasks '
            f'({start + 1}-{start + len(batch)} of {len(targets)})...'
        )
        task_ids = _queue_batch(batch)
        _wait_for_batch(task_ids, poll_interval)
        print(f'Batch {batch_num}/{total_batches} done.')

    print('All batches complete.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Report how many variants would be re-queued without queuing anything.',
    )
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument(
        '--poll-interval',
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help='Seconds between checks that a batch has finished (default: %(default)s).',
    )
    args = parser.parse_args()
    try:
        requeue(
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            poll_interval=args.poll_interval,
        )
    except KeyboardInterrupt:
        print('Interrupted.', file=sys.stderr)
        sys.exit(1)
