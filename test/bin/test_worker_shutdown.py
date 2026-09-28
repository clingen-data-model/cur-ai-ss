"""Graceful SIGTERM/SIGINT handling: in-flight leases get released instead of
sitting RUNNING until the lease timeout notices them."""

import pytest

from lib.bin import worker
from lib.models import GeneDB, PaperDB, TaskDB
from lib.tasks.models import TaskStatus, TaskType

TYPE = TaskType.PDF_PARSING


@pytest.fixture
def running_task(db_session):
    def _make(tries: int) -> TaskDB:
        gene = GeneDB(symbol='BRCA1')
        db_session.add(gene)
        db_session.flush()
        paper = PaperDB(
            gene_id=gene.id, filename='p.pdf', content_hash='h', title='A paper'
        )
        db_session.add(paper)
        db_session.flush()
        task = TaskDB(
            paper_id=paper.id, type=TYPE, status=TaskStatus.RUNNING, tries=tries
        )
        db_session.add(task)
        db_session.commit()
        return task

    return _make


async def test_release_resets_a_retriable_task_to_pending(
    db_session, running_task, monkeypatch
):
    task = running_task(tries=1)
    monkeypatch.setattr(worker, '_in_flight_tasks', {task.id})

    await worker._release_in_flight_tasks()

    db_session.expire_all()
    refreshed = db_session.get(TaskDB, task.id)
    assert refreshed.status == TaskStatus.PENDING


async def test_release_abandons_a_task_that_exhausted_retries(
    db_session, running_task, monkeypatch
):
    task = running_task(tries=worker.MAX_RETRIES)
    monkeypatch.setattr(worker, '_in_flight_tasks', {task.id})

    await worker._release_in_flight_tasks()

    db_session.expire_all()
    refreshed = db_session.get(TaskDB, task.id)
    assert refreshed.status == TaskStatus.FAILED
    assert refreshed.error_message == 'Worker shut down mid-task and exhausted retries'


async def test_release_is_a_noop_with_nothing_in_flight(monkeypatch):
    monkeypatch.setattr(worker, '_in_flight_tasks', set())
    await worker._release_in_flight_tasks()  # must not raise


async def test_execute_task_tracks_the_task_as_in_flight_only_while_running(
    db_session, running_task, monkeypatch
):
    task = running_task(tries=0)
    db_session.get(TaskDB, task.id).status = TaskStatus.PENDING
    db_session.commit()
    monkeypatch.setattr(worker, '_in_flight_tasks', set())

    seen_in_flight = False

    async def run(task_id: int) -> None:
        nonlocal seen_in_flight
        seen_in_flight = task_id in worker._in_flight_tasks

    monkeypatch.setitem(worker.TASK_HANDLERS, TYPE, run)

    await worker.execute_task(task.id)

    assert seen_in_flight
    assert task.id not in worker._in_flight_tasks
