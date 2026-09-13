"""run_id: one user action, plus everything it cascades into."""

import datetime

import pytest

from lib.models import GeneDB, PaperDB, TaskDB
from lib.tasks.misc import (
    enqueue_all_instances,
    enqueue_successors,
    enqueue_task,
    invalidate_descendants,
)
from lib.tasks.models import TaskStatus, TaskType


@pytest.fixture
def paper(db_session):
    gene = GeneDB(symbol='BRCA1')
    db_session.add(gene)
    db_session.flush()
    row = PaperDB(gene_id=gene.id, filename='p.pdf', content_hash='h')
    db_session.add(row)
    db_session.flush()
    return row


def _run_ids(db_session, paper, task_type=None):
    q = db_session.query(TaskDB).filter(TaskDB.paper_id == paper.id)
    if task_type:
        q = q.filter(TaskDB.type == task_type)
    return {t.type: t.run_id for t in q}


def test_a_task_enqueued_with_no_run_starts_one(db_session, paper):
    task = enqueue_task(db_session, paper.id, TaskType.PDF_PARSING)

    assert task.run_id


def test_successors_inherit_the_run_that_produced_them(db_session, paper):
    """This inheritance is what makes a run a connected subtree rather than a
    single task."""
    root = enqueue_task(db_session, paper.id, TaskType.PDF_PARSING)
    root.status = TaskStatus.COMPLETED
    db_session.flush()

    enqueue_successors(db_session, root)

    successors = _run_ids(db_session, paper, TaskType.PAPER_CLASSIFIER)
    assert successors
    assert set(successors.values()) == {root.run_id}


def test_a_rerun_gives_descendants_a_new_run(db_session, paper):
    """The question this file exists to answer: descendants of a re-run carry
    the new id, not the one they had before."""
    root = enqueue_task(db_session, paper.id, TaskType.PDF_PARSING)
    first_run = root.run_id
    root.status = TaskStatus.COMPLETED
    db_session.flush()
    enqueue_successors(db_session, root)
    assert _run_ids(db_session, paper)[TaskType.PAPER_CLASSIFIER] == first_run

    # Re-run the root: descendants are cleared, then recreated under a new run.
    invalidate_descendants(db_session, paper.id, TaskType.PDF_PARSING)
    rerun = enqueue_task(db_session, paper.id, TaskType.PDF_PARSING, run_id='run-2')
    rerun.status = TaskStatus.COMPLETED
    db_session.flush()
    enqueue_successors(db_session, rerun)

    ids = _run_ids(db_session, paper)
    assert ids[TaskType.PDF_PARSING] == 'run-2'
    assert ids[TaskType.PAPER_CLASSIFIER] == 'run-2'
    assert first_run not in ids.values()


def test_reusing_an_existing_row_reassigns_its_run(db_session, paper):
    """enqueue_task resets a matching row rather than always inserting, so the
    run has to be reassigned -- otherwise a re-run would be dated to the run
    whose row it happened to reuse."""
    first = enqueue_task(db_session, paper.id, TaskType.PDF_PARSING)
    first.status = TaskStatus.COMPLETED
    db_session.flush()

    again = enqueue_task(db_session, paper.id, TaskType.PDF_PARSING, run_id='run-2')

    assert again.id == first.id, 'expected the row to be reused'
    assert again.run_id == 'run-2'


def test_ancestors_keep_their_own_run(db_session, paper):
    """invalidate_descendants only clears downstream, so upstream rows survive a
    re-run -- and they belong to the run that created them, not this one."""
    root = enqueue_task(db_session, paper.id, TaskType.PDF_PARSING)
    first_run = root.run_id
    root.status = TaskStatus.COMPLETED
    db_session.flush()
    enqueue_successors(db_session, root)

    classifier = (
        db_session.query(TaskDB).filter(TaskDB.type == TaskType.PAPER_CLASSIFIER).one()
    )
    enqueue_task(db_session, paper.id, TaskType.PAPER_CLASSIFIER, run_id='run-2')

    assert classifier.run_id == 'run-2'
    # The root was never downstream of the re-run, so it keeps its own.
    assert _run_ids(db_session, paper)[TaskType.PDF_PARSING] == first_run


def test_enqueue_all_instances_reassigns_the_run(db_session, paper):
    """The path POST /papers/{id}/tasks actually takes.

    create_task mints a run id and hands it to enqueue_all_instances, which
    found the existing row, reset it, and dropped the id on the floor -- so a
    re-run joined the run it was replacing, and its elapsed time was measured
    from whenever that one started. Every test here used enqueue_task, which
    does assign it, so the gap sat under passing coverage.
    """
    first = enqueue_task(db_session, paper.id, TaskType.PDF_PARSING)
    first.status = TaskStatus.COMPLETED
    db_session.flush()

    rerun = enqueue_all_instances(
        db_session, paper.id, TaskType.PDF_PARSING, run_id='run-2'
    )

    assert [t.run_id for t in rerun] == ['run-2']


def test_requeuing_clears_the_previous_attempts_start_time(db_session, paper):
    """started_at is what the progress bars measure elapsed time from, so a
    task carrying the last run's start renders as a bar parked at 99% before
    anything has begun. execute_task stamps it again when a handler starts."""
    task = enqueue_task(db_session, paper.id, TaskType.PDF_PARSING)
    task.status = TaskStatus.COMPLETED
    task.started_at = datetime.datetime(
        2026, 9, 13, 21, 45, tzinfo=datetime.timezone.utc
    )
    db_session.flush()

    assert enqueue_task(db_session, paper.id, TaskType.PDF_PARSING).started_at is None


def test_requeuing_all_instances_clears_the_start_time_too(db_session, paper):
    """Same row, the other entry point -- and the one the endpoint uses."""
    task = enqueue_task(db_session, paper.id, TaskType.PDF_PARSING)
    task.status = TaskStatus.FAILED
    task.started_at = datetime.datetime(
        2026, 9, 13, 21, 45, tzinfo=datetime.timezone.utc
    )
    db_session.flush()

    rerun = enqueue_all_instances(db_session, paper.id, TaskType.PDF_PARSING)

    assert [t.started_at for t in rerun] == [None]
