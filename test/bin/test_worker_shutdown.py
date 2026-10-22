"""Claimed tasks are swept back to PENDING on shutdown and on startup, instead
of sitting QUEUED or RUNNING until the lease timeout notices them."""

import asyncio

import pytest

from lib.bin import worker
from lib.models import GeneDB, PaperDB, TaskDB
from lib.tasks.models import TaskStatus, TaskType

TYPE = TaskType.PDF_PARSING


@pytest.fixture
def make_task(db_session):
    gene = GeneDB(symbol='BRCA1')
    db_session.add(gene)
    db_session.flush()
    paper = PaperDB(
        gene_id=gene.id, filename='p.pdf', content_hash='h', title='A paper'
    )
    db_session.add(paper)
    db_session.flush()

    def _make(status: TaskStatus, tries: int = 0) -> TaskDB:
        task = TaskDB(paper_id=paper.id, type=TYPE, status=status, tries=tries)
        db_session.add(task)
        db_session.commit()
        return task

    return _make


@pytest.fixture
def cleared(monkeypatch) -> list[int]:
    ids: list[int] = []

    async def record(task_id: int) -> None:
        ids.append(task_id)

    monkeypatch.setattr(worker, 'clear_task_session', record)
    return ids


@pytest.fixture
def not_shutting_down(monkeypatch):
    monkeypatch.setattr(worker, '_shutting_down', False)


def _status(db_session, task_id: int) -> TaskDB:
    db_session.expire_all()
    return db_session.get(TaskDB, task_id)


async def test_sweep_resets_a_running_task_with_a_retry_left_and_clears_its_session(
    db_session, make_task, cleared
):
    task = make_task(TaskStatus.RUNNING, tries=1)

    assert await worker._sweep_claimed_tasks('shut down') == 1

    assert _status(db_session, task.id).status == TaskStatus.PENDING
    assert cleared == [task.id]


async def test_sweep_abandons_a_running_task_on_its_last_try_naming_the_event(
    db_session, make_task, cleared
):
    task = make_task(TaskStatus.RUNNING, tries=worker.MAX_RETRIES)

    await worker._sweep_claimed_tasks('restarted')

    refreshed = _status(db_session, task.id)
    assert refreshed.status == TaskStatus.FAILED
    assert refreshed.error_message == 'Worker restarted mid-task and exhausted retries'
    assert cleared == []


async def test_sweep_resets_a_queued_task_whatever_its_tries_without_clearing(
    db_session, make_task, cleared
):
    # QUEUED never started an attempt, so it has no session and nothing to count.
    task = make_task(TaskStatus.QUEUED, tries=worker.MAX_RETRIES)

    await worker._sweep_claimed_tasks('shut down')

    assert _status(db_session, task.id).status == TaskStatus.PENDING
    assert cleared == []


async def test_sweep_leaves_settled_and_pending_rows_alone(
    db_session, make_task, cleared
):
    rows = [
        make_task(TaskStatus.PENDING),
        make_task(TaskStatus.COMPLETED, tries=1),
        make_task(TaskStatus.FAILED, tries=3),
    ]

    assert await worker._sweep_claimed_tasks('shut down') == 0

    for row, expected in zip(
        rows, (TaskStatus.PENDING, TaskStatus.COMPLETED, TaskStatus.FAILED)
    ):
        assert _status(db_session, row.id).status == expected
    assert cleared == []


async def test_execute_task_declines_to_claim_while_shutting_down(
    db_session, make_task, monkeypatch
):
    task = make_task(TaskStatus.QUEUED, tries=1)
    monkeypatch.setattr(worker, '_shutting_down', True)
    ran = False

    async def run(task_id: int) -> None:
        nonlocal ran
        ran = True

    monkeypatch.setitem(worker.TASK_HANDLERS, TYPE, run)

    await worker.execute_task(task.id)

    assert not ran
    refreshed = _status(db_session, task.id)
    assert refreshed.status == TaskStatus.QUEUED  # left for the sweep
    assert refreshed.tries == 1  # the attempt that never started costs nothing


async def test_execute_task_runs_a_claimed_task_when_not_shutting_down(
    db_session, make_task, not_shutting_down, monkeypatch
):
    task = make_task(TaskStatus.QUEUED)
    ran = False

    async def run(task_id: int) -> None:
        nonlocal ran
        ran = True

    monkeypatch.setitem(worker.TASK_HANDLERS, TYPE, run)

    await worker.execute_task(task.id)

    assert ran
    assert _status(db_session, task.id).status == TaskStatus.COMPLETED


async def test_the_poller_claims_nothing_once_shutting_down(
    db_session, make_task, monkeypatch
):
    task = make_task(TaskStatus.PENDING)
    monkeypatch.setattr(worker, '_shutting_down', True)
    semaphores = {t: asyncio.Semaphore(1) for t in TaskType}

    await worker.poll_and_schedule_tasks(asyncio.Semaphore(1), semaphores)

    assert _status(db_session, task.id).status == TaskStatus.PENDING


async def test_the_signal_handler_sets_the_flag_and_schedules_one_shutdown(
    monkeypatch, not_shutting_down
):
    scheduled: list[object] = []

    def fake_create_task(coro: object) -> None:
        scheduled.append(coro)
        coro.close()  # type: ignore[attr-defined]

    monkeypatch.setattr(worker.asyncio, 'create_task', fake_create_task)

    # systemd signals the whole control group, so the handler fires more than once
    worker._handle_shutdown_signal(15)
    worker._handle_shutdown_signal(15)

    assert worker._shutting_down is True
    assert len(scheduled) == 1
