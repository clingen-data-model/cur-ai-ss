#!/usr/bin/env python3
"""Re-run the extraction pipeline on a set of papers, e.g. after changing
EXTRACTION_MODEL, and wait for each batch to finish.

Takes the same path as the "Rerun Agents" button (``POST /papers/{id}/tasks``):
refuse a paper with a task in flight, snapshot it, delete the previous run's
downstream task rows, then re-queue the starting task so the worker cascades
through its successors. PDF parsing is not re-run unless asked for with
``--from-task``.

Papers are chosen by PMID, from the ``PMID`` column of a CSV (default: the
training set, ``var/training_papers.csv``), and/or by ``--paper-id``.

To compare a new model against the old one, write baseline snapshots *before*
deploying the change::

    uv run python -m lib.bin.requeue_papers --snapshot-only

A snapshot records ``model`` from the environment of the process that writes it,
not from whatever produced the data. A "before" snapshot written by this script
after EXTRACTION_MODEL changed would therefore label the old results with the
new model -- unless the paper's latest snapshot already matches its current
state, in which case none is written. The pipeline writes one when it completes,
so for a paper that finished cleanly and was not edited afterwards this is moot;
``--snapshot-only`` makes it certain, and reports which papers got a new one.

Requires the worker (``./bin/worker`` locally, or the ``worker`` systemd user
unit on dev-caa) to be running -- this script only enqueues tasks.

Usage:
    uv run python -m lib.bin.requeue_papers [--snapshot-only] [--dry-run]
        [--pmids-file CSV] [--paper-id N ...] [--from-task "Paper Classifier"]
        [--batch-size N] [--poll-interval SECONDS]
"""

import argparse
import csv
import sys
import time
from collections import Counter
from pathlib import Path

from sqlalchemy.orm import Session

from lib.api.db import session_scope
from lib.misc.snapshots import write_snapshot_safe
from lib.models import PaperDB
from lib.tasks.misc import (
    enqueue_all_instances,
    invalidate_descendants,
    paper_busy_message,
)
from lib.tasks.models import ACTIVE_STATUSES, TaskDB, TaskStatus, TaskType

DEFAULT_PMIDS_FILE = Path('var/training_papers.csv')
DEFAULT_FROM_TASK = TaskType.PAPER_CLASSIFIER
# A whole-paper rerun is dozens of LLM calls; the worker's own per-task
# concurrency limits still govern how many run at once.
DEFAULT_BATCH_SIZE = 5
DEFAULT_POLL_INTERVAL_SECONDS = 10.0
# The worker creates a task's successors as it completes the task, so a paper
# can look idle for an instant between two steps. Require this many consecutive
# idle polls before calling a batch finished.
QUIET_POLLS = 2


def read_pmids(path: Path) -> list[str]:
    with open(path, newline='') as fp:
        return [
            pmid
            for row in csv.DictReader(fp)
            if (pmid := (row.get('PMID') or '').strip())
        ]


def resolve_papers(
    session: Session, pmids: list[str], paper_ids: list[int]
) -> tuple[list[int], list[str]]:
    """(paper ids to run, PMIDs that matched no paper), ids in ascending order."""
    found: dict[str, int] = {}
    matched: set[int] = set()
    if pmids:
        for paper in session.query(PaperDB).filter(PaperDB.pmid.in_(pmids)):
            matched.add(paper.id)
            if paper.pmid is not None:
                found[paper.pmid] = paper.id
    missing = [pmid for pmid in pmids if pmid not in found]
    for paper_id in paper_ids:
        if session.get(PaperDB, paper_id) is None:
            raise SystemExit(f'No paper with id {paper_id}.')
        matched.add(paper_id)
    return sorted(matched), missing


def snapshot_paper(session: Session, paper_id: int, description: str) -> str | None:
    """Why this paper can't be handled yet, or None once it has been snapshotted."""
    busy = paper_busy_message(session, paper_id, 're-running')
    if busy:
        return busy
    write_snapshot_safe(session, paper_id, description=description)
    return None


def requeue_paper(
    session: Session, paper_id: int, task_type: TaskType, description: str
) -> str | None:
    """Re-run ``task_type`` and everything downstream. Returns a reason if skipped."""
    skipped = snapshot_paper(session, paper_id, description)
    if skipped:
        return skipped
    invalidate_descendants(session, paper_id, task_type)
    enqueue_all_instances(
        session, paper_id=paper_id, task_type=task_type, updated_by_user_id=None
    )
    return None


def _active_task_count(paper_ids: list[int]) -> int:
    with session_scope() as session:
        return (
            session.query(TaskDB)
            .filter(TaskDB.paper_id.in_(paper_ids))
            .filter(TaskDB.status.in_(ACTIVE_STATUSES))
            .count()
        )


def _wait_for_idle(paper_ids: list[int], poll_interval: float) -> None:
    quiet = 0
    while quiet < QUIET_POLLS:
        active = _active_task_count(paper_ids)
        if active == 0:
            quiet += 1
        else:
            quiet = 0
            print(f'    {active} tasks still active...')
        time.sleep(poll_interval)


def _report(paper_ids: list[int]) -> int:
    """Print each paper's task outcome; returns how many failed tasks there were."""
    failed_total = 0
    with session_scope() as session:
        for paper_id in paper_ids:
            tasks = session.query(TaskDB).filter(TaskDB.paper_id == paper_id).all()
            counts = Counter(t.status.value for t in tasks)
            failed = [t for t in tasks if t.status == TaskStatus.FAILED]
            failed_total += len(failed)
            summary = ', '.join(f'{n} {s}' for s, n in sorted(counts.items()))
            print(f'  paper {paper_id}: {summary or "no tasks"}')
            for task in failed:
                print(
                    f'    FAILED {task.type.value}: {(task.error_message or "")[:160]}'
                )
    return failed_total


def run(
    paper_ids: list[int],
    task_type: TaskType,
    *,
    snapshot_only: bool,
    batch_size: int,
    poll_interval: float,
) -> None:
    total_batches = (len(paper_ids) + batch_size - 1) // batch_size
    skipped: dict[int, str] = {}
    failed_total = 0
    for batch_num, start in enumerate(range(0, len(paper_ids), batch_size), start=1):
        batch = paper_ids[start : start + batch_size]
        print(f'Batch {batch_num}/{total_batches}: papers {batch}')
        queued = []
        for paper_id in batch:
            with session_scope() as session:
                if snapshot_only:
                    reason = snapshot_paper(
                        session, paper_id, 'Baseline before changing the model'
                    )
                else:
                    reason = requeue_paper(
                        session,
                        paper_id,
                        task_type,
                        f'Before re-running {task_type.value}',
                    )
            if reason:
                skipped[paper_id] = reason
                print(f'  paper {paper_id}: SKIPPED -- {reason}')
            else:
                queued.append(paper_id)
        if queued and not snapshot_only:
            _wait_for_idle(queued, poll_interval)
            failed_total += _report(queued)
        print(f'Batch {batch_num}/{total_batches} done.')

    verb = 'snapshotted' if snapshot_only else 're-run'
    print(f'{len(paper_ids) - len(skipped)} of {len(paper_ids)} papers {verb}.')
    if skipped:
        print(f'Skipped (still busy): {sorted(skipped)}. Re-run when idle.')
    if failed_total:
        print(f'{failed_total} task(s) failed; see above.')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument(
        '--pmids-file',
        type=Path,
        default=None,
        help=f'CSV with a PMID column (default: {DEFAULT_PMIDS_FILE}, unless '
        '--paper-id is given).',
    )
    parser.add_argument(
        '--paper-id',
        type=int,
        action='append',
        default=[],
        help='Run this paper id (repeatable); replaces the default PMID file.',
    )
    parser.add_argument(
        '--from-task',
        type=TaskType,
        default=DEFAULT_FROM_TASK,
        metavar='TASK',
        help='Task to re-queue; everything downstream of it re-runs. One of: '
        + ', '.join(repr(t.value) for t in TaskType)
        + " (default: 'Paper Classifier').",
    )
    parser.add_argument(
        '--snapshot-only',
        action='store_true',
        help='Write a baseline snapshot per paper and stop; queue nothing.',
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument(
        '--poll-interval', type=float, default=DEFAULT_POLL_INTERVAL_SECONDS
    )
    args = parser.parse_args()

    pmids_file = args.pmids_file or (None if args.paper_id else DEFAULT_PMIDS_FILE)
    pmids = read_pmids(pmids_file) if pmids_file else []
    with session_scope() as session:
        paper_ids, missing = resolve_papers(session, pmids, args.paper_id)

    print(
        f'{len(paper_ids)} papers to {"snapshot" if args.snapshot_only else "re-run"}.'
    )
    if missing:
        print(f'No paper found for PMID(s): {", ".join(missing)}')
    if not paper_ids:
        return
    if args.dry_run:
        print(f'Dry run: papers {paper_ids}; nothing queued.')
        return
    try:
        run(
            paper_ids,
            args.from_task,
            snapshot_only=args.snapshot_only,
            batch_size=args.batch_size,
            poll_interval=args.poll_interval,
        )
    except KeyboardInterrupt:
        print('Interrupted; tasks already queued keep running.', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
