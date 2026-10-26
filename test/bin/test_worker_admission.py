"""Admission is decided from the tasks table: a poll starts as many PENDING
tasks as the RUNNING counts leave room for, and claiming a task is starting
it. The per-(paper, type) fan-out gate -- the first task of a batch runs
alone so its request writes the prompt-cache entry before the rest start --
is decided from the same table."""

import asyncio
import datetime

import pytest

from lib.bin import worker
from lib.models import GeneDB, PaperDB, TaskDB
from lib.tasks.models import TaskStatus, TaskType

TYPE = TaskType.PATIENT_DEMOGRAPHICS


@pytest.fixture
def papers(db_session) -> list[PaperDB]:
    gene = GeneDB(symbol='BRCA1')
    db_session.add(gene)
    db_session.flush()
    rows = [
        PaperDB(gene_id=gene.id, filename=f'{n}.pdf', content_hash=f'h{n}', title=n)
        for n in ('one', 'two')
    ]
    db_session.add_all(rows)
    db_session.commit()
    return rows


@pytest.fixture
def make_task(db_session, papers):
    def _make(
        status: TaskStatus = TaskStatus.PENDING,
        task_type: TaskType = TYPE,
        paper: PaperDB | None = None,
        finished_ago_s: int | None = None,
    ) -> TaskDB:
        task = TaskDB(
            paper_id=(paper or papers[0]).id, type=task_type, status=status, tries=0
        )
        if status == TaskStatus.RUNNING:
            task.tries = 1
            task.started_at = datetime.datetime.now(datetime.timezone.utc)
        if finished_ago_s is not None:
            task.updated_at = datetime.datetime.now(
                datetime.timezone.utc
            ) - datetime.timedelta(seconds=finished_ago_s)
        db_session.add(task)
        db_session.commit()
        return task

    return _make


@pytest.fixture
def started(monkeypatch) -> list[int]:
    """Record which attempts the poll started, without running any handler,
    so rows stay RUNNING for the next poll to count."""
    monkeypatch.setattr(worker, '_shutting_down', False)
    monkeypatch.setattr(worker, '_attempts', {})  # see test_worker_shutdown
    ids: list[int] = []

    async def record(task_id: int, attempt: int) -> None:
        ids.append(task_id)

    monkeypatch.setattr(worker, 'execute_task', record)
    return ids


async def _poll() -> None:
    await worker.poll_and_schedule_tasks()
    await asyncio.sleep(0)  # the poll only schedules execute_task; let it run


def _status(db_session, task_id: int) -> TaskDB:
    db_session.expire_all()
    return db_session.get(TaskDB, task_id)


async def test_claiming_a_task_is_starting_it(db_session, make_task, started):
    task = make_task()

    await _poll()

    assert started == [task.id]
    row = _status(db_session, task.id)
    assert row.status == TaskStatus.RUNNING
    assert row.tries == 1
    assert row.started_at is not None
    assert row.started_at == row.updated_at


async def test_a_type_admits_only_what_its_limit_leaves_free(
    db_session, make_task, started, papers
):
    # PDF Parsing runs one at a time; the first poll starts one, the next
    # starts nothing while it runs, and the one after it finishes starts the other.
    first = make_task(task_type=TaskType.PDF_PARSING, paper=papers[0])
    second = make_task(task_type=TaskType.PDF_PARSING, paper=papers[1])

    await _poll()
    assert started == [first.id]

    await _poll()
    assert started == [first.id]

    _status(db_session, first.id).status = TaskStatus.COMPLETED
    db_session.commit()
    await _poll()
    assert started == [first.id, second.id]


async def test_the_global_limit_counts_every_running_attempt(
    db_session, make_task, started, papers, monkeypatch
):
    monkeypatch.setattr(worker, 'GLOBAL_CONCURRENCY', 2)
    make_task(status=TaskStatus.RUNNING, task_type=TaskType.VARIANT_EXTRACTION)
    a = make_task(paper=papers[0])
    make_task(paper=papers[1])

    await _poll()

    assert started == [a.id]


async def test_the_first_task_of_a_batch_runs_alone_until_it_finishes(
    db_session, make_task, started
):
    tasks = [make_task() for _ in range(3)]

    await _poll()
    assert started == [tasks[0].id]

    await _poll()
    assert started == [tasks[0].id]  # still warming the cache

    _status(db_session, tasks[0].id).status = TaskStatus.COMPLETED
    db_session.commit()
    await _poll()
    assert started == [t.id for t in tasks]


async def test_a_failed_first_task_still_opens_the_gate(db_session, make_task, started):
    make_task(status=TaskStatus.FAILED, finished_ago_s=5)
    rest = [make_task() for _ in range(2)]

    await _poll()

    assert started == [t.id for t in rest]


async def test_an_expired_window_serialises_the_first_task_again(
    db_session, make_task, started
):
    make_task(status=TaskStatus.COMPLETED, finished_ago_s=worker.CACHE_WARM_S + 60)
    rest = [make_task() for _ in range(2)]

    await _poll()

    assert started == [rest[0].id]


async def test_other_papers_and_types_are_not_held(
    db_session, make_task, started, papers
):
    a = make_task(paper=papers[0])
    make_task(paper=papers[0])
    b = make_task(paper=papers[1])
    c = make_task(paper=papers[0], task_type=TaskType.VARIANT_EXTRACTION)

    await _poll()

    assert sorted(started) == sorted([a.id, b.id, c.id])


async def test_a_retired_attempt_does_not_write_its_outcome(
    db_session, make_task, monkeypatch
):
    """The lease sweep reset the row while the attempt was still running:
    the retry is the current attempt, and the stale one's result is dropped."""
    monkeypatch.setattr(worker, '_shutting_down', False)
    task = make_task(status=TaskStatus.RUNNING)  # attempt 1
    successors: list[int] = []
    monkeypatch.setattr(
        worker, 'enqueue_successors', lambda session, t: successors.append(t.id)
    )

    async def run(task_id: int) -> None:
        row = _status(db_session, task_id)
        row.status = TaskStatus.PENDING  # the sweep retiring attempt 1
        db_session.commit()

    monkeypatch.setitem(worker.TASK_HANDLERS, TYPE, run)

    await worker.execute_task(task.id, attempt=1)

    assert _status(db_session, task.id).status == TaskStatus.PENDING
    assert successors == []
