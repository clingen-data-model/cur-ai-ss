"""The tasks table is shared by WORKER_COUNT worker processes, each owning the
papers whose id % WORKER_COUNT is its WORKER_ID. Every query the worker runs
over the table carries that filter (shard_filter), so one worker's sweeps
never release another's live attempts, and admission counts only its own."""

import asyncio
import datetime

import pytest

from lib.bin import worker
from lib.core.environment import Env
from lib.models import GeneDB, PaperDB, TaskDB
from lib.tasks.models import TaskStatus, TaskType

TYPE = TaskType.PATIENT_DEMOGRAPHICS
COUNT = 4


@pytest.fixture
def papers(db_session) -> list[PaperDB]:
    """One paper per shard, so each worker owns exactly one of them."""
    gene = GeneDB(symbol='BRCA1')
    db_session.add(gene)
    db_session.flush()
    rows = [
        PaperDB(
            gene_id=gene.id, filename=f'{n}.pdf', content_hash=f'h{n}', title=str(n)
        )
        for n in range(COUNT)
    ]
    db_session.add_all(rows)
    db_session.commit()
    assert sorted(row.id % COUNT for row in rows) == list(range(COUNT))
    return rows


@pytest.fixture
def mine(papers) -> PaperDB:
    return next(row for row in papers if row.id % COUNT == 1)


@pytest.fixture
def theirs(papers) -> PaperDB:
    return next(row for row in papers if row.id % COUNT == 2)


@pytest.fixture
def this_worker(monkeypatch):
    monkeypatch.setattr(worker.env, 'WORKER_COUNT', COUNT)
    monkeypatch.setattr(worker.env, 'WORKER_ID', 1)
    monkeypatch.setattr(worker, '_shutting_down', False)
    monkeypatch.setattr(worker, '_attempts', {})


@pytest.fixture
def make_task(db_session):
    def _make(
        paper: PaperDB,
        status: TaskStatus = TaskStatus.PENDING,
        tries: int = 0,
        started_ago_s: int | None = None,
        updated_ago_s: int | None = None,
    ) -> TaskDB:
        now = datetime.datetime.now(datetime.timezone.utc)
        task = TaskDB(paper_id=paper.id, type=TYPE, status=status, tries=tries)
        if started_ago_s is not None:
            task.started_at = now - datetime.timedelta(seconds=started_ago_s)
        if updated_ago_s is not None:
            task.updated_at = now - datetime.timedelta(seconds=updated_ago_s)
        db_session.add(task)
        db_session.commit()
        return task

    return _make


@pytest.fixture
def started(monkeypatch) -> list[int]:
    ids: list[int] = []

    async def record(task_id: int, attempt: int) -> None:
        ids.append(task_id)

    monkeypatch.setattr(worker, 'execute_task', record)
    return ids


@pytest.fixture
def cleared(monkeypatch) -> list[int]:
    ids: list[int] = []

    async def record(task_id: int) -> None:
        ids.append(task_id)

    monkeypatch.setattr(worker, 'clear_task_session', record)
    return ids


def _status(db_session, task_id: int) -> TaskStatus:
    db_session.expire_all()
    return db_session.get(TaskDB, task_id).status


async def _poll() -> None:
    await worker.poll_and_schedule_tasks()
    await asyncio.sleep(0)


async def test_the_poll_claims_only_the_pending_tasks_of_its_shard(
    db_session, this_worker, make_task, started, mine, theirs
):
    own = make_task(mine)
    other = make_task(theirs)

    await _poll()

    assert started == [own.id]
    assert _status(db_session, own.id) == TaskStatus.RUNNING
    assert _status(db_session, other.id) == TaskStatus.PENDING


async def test_another_shards_running_rows_do_not_count_against_the_limits(
    db_session, this_worker, make_task, started, mine, theirs, monkeypatch
):
    monkeypatch.setattr(worker, 'GLOBAL_CONCURRENCY', 1)
    make_task(theirs, status=TaskStatus.RUNNING, tries=1, started_ago_s=1)
    own = make_task(mine)

    await _poll()

    assert started == [own.id]


async def test_the_sweep_releases_only_this_shards_running_attempts(
    db_session, this_worker, make_task, cleared, mine, theirs
):
    own = make_task(mine, status=TaskStatus.RUNNING, tries=1, started_ago_s=1)
    other = make_task(theirs, status=TaskStatus.RUNNING, tries=1, started_ago_s=1)

    swept = await worker._sweep_claimed_tasks('restarted')

    assert swept == 1
    assert cleared == [own.id]
    assert _status(db_session, own.id) == TaskStatus.PENDING
    # Another worker's live attempt: resetting it would run the task twice.
    assert _status(db_session, other.id) == TaskStatus.RUNNING


async def test_the_lease_sweep_retires_only_this_shards_expired_attempts(
    db_session, this_worker, make_task, started, cleared, mine, theirs
):
    expired = worker.DEFAULT_LEASE_TIMEOUT_S + 60
    own = make_task(mine, status=TaskStatus.RUNNING, tries=1, started_ago_s=expired)
    other = make_task(theirs, status=TaskStatus.RUNNING, tries=1, started_ago_s=expired)

    await _poll()

    assert cleared == [own.id]
    # Retired and, with a retry left, restarted by the same poll.
    assert started == [own.id]
    assert _status(db_session, other.id) == TaskStatus.RUNNING


async def test_the_retry_sweep_revives_only_this_shards_failed_tasks(
    db_session, this_worker, make_task, started, cleared, mine, theirs
):
    long_ago = worker.RETRY_DELAY_S + 60
    own = make_task(mine, status=TaskStatus.FAILED, tries=1, updated_ago_s=long_ago)
    other = make_task(theirs, status=TaskStatus.FAILED, tries=1, updated_ago_s=long_ago)

    await _poll()

    assert cleared == [own.id]
    assert started == [own.id]
    assert _status(db_session, other.id) == TaskStatus.FAILED


@pytest.mark.parametrize(
    'worker_id, worker_count',
    [(4, 4), (-1, 4), (0, 0)],
)
def test_a_worker_id_outside_its_count_is_refused(worker_id, worker_count, monkeypatch):
    monkeypatch.setenv('WORKER_ID', str(worker_id))
    monkeypatch.setenv('WORKER_COUNT', str(worker_count))
    with pytest.raises(ValueError, match='WORKER_'):
        Env()
