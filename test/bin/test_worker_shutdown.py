"""Running tasks are swept back to PENDING on shutdown and on startup, instead
of sitting RUNNING until the lease timeout notices them."""

import datetime

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


@pytest.fixture(autouse=True)
def fresh_attempts(monkeypatch):
    # Each test gets its own event loop, which closes before the done
    # callbacks of the attempts it launched can run; the worker's one loop
    # lives as long as the process, so this is test hygiene only.
    monkeypatch.setattr(worker, '_attempts', {})


def _status(db_session, task_id: int) -> TaskDB:
    db_session.expire_all()
    return db_session.get(TaskDB, task_id)


@pytest.mark.parametrize('tries', [1, worker.MAX_RETRIES])
async def test_sweep_resets_a_running_task_with_a_retry_left_and_clears_its_session(
    db_session, make_task, cleared, tries
):
    # tries == MAX_RETRIES is the boundary: that many attempts have started,
    # and one more is owed, the same rule the retry sweep applies to FAILED.
    task = make_task(TaskStatus.RUNNING, tries=tries)

    assert await worker._sweep_claimed_tasks('shut down') == 1

    assert _status(db_session, task.id).status == TaskStatus.PENDING
    assert cleared == [task.id]


async def test_sweep_abandons_a_running_task_on_its_last_try_naming_the_event(
    db_session, make_task, cleared
):
    task = make_task(TaskStatus.RUNNING, tries=worker.MAX_RETRIES + 1)

    await worker._sweep_claimed_tasks('restarted')

    refreshed = _status(db_session, task.id)
    assert refreshed.status == TaskStatus.FAILED
    assert refreshed.error_message == 'Worker restarted mid-task and exhausted retries'
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


async def test_execute_task_declines_to_run_while_shutting_down(
    db_session, make_task, monkeypatch
):
    task = make_task(TaskStatus.RUNNING, tries=1)
    monkeypatch.setattr(worker, '_shutting_down', True)
    ran = False

    async def run(task_id: int) -> None:
        nonlocal ran
        ran = True

    monkeypatch.setitem(worker.TASK_HANDLERS, TYPE, run)

    await worker.execute_task(task.id, attempt=1)

    assert not ran
    assert _status(db_session, task.id).status == TaskStatus.RUNNING  # for the sweep


async def test_execute_task_runs_a_started_attempt_when_not_shutting_down(
    db_session, make_task, not_shutting_down, monkeypatch
):
    task = make_task(TaskStatus.RUNNING, tries=1)
    ran = False

    async def run(task_id: int) -> None:
        nonlocal ran
        ran = True

    monkeypatch.setitem(worker.TASK_HANDLERS, TYPE, run)

    await worker.execute_task(task.id, attempt=1)

    assert ran
    assert _status(db_session, task.id).status == TaskStatus.COMPLETED


async def test_the_poller_claims_nothing_once_shutting_down(
    db_session, make_task, monkeypatch
):
    task = make_task(TaskStatus.PENDING)
    monkeypatch.setattr(worker, '_shutting_down', True)

    await worker.poll_and_schedule_tasks()

    assert _status(db_session, task.id).status == TaskStatus.PENDING


async def test_the_lease_timeout_holds_each_task_to_its_own_types_limit(
    db_session, make_task, cleared, not_shutting_down, monkeypatch
):
    # Both started 25 min ago: past the default 20 min, within PDF Parsing's 30.
    parse = make_task(TaskStatus.RUNNING, tries=1)
    agent = make_task(TaskStatus.RUNNING, tries=1)
    agent.type = TaskType.PATIENT_DEMOGRAPHICS
    began = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        minutes=25
    )
    for task in (parse, agent):
        task.started_at = began
    db_session.commit()

    async def no_run(task_id: int, attempt: int) -> None:
        return None

    monkeypatch.setattr(worker, 'execute_task', no_run)

    await worker.poll_and_schedule_tasks()

    assert cleared == [agent.id]  # retired, session cleared, then started again
    assert _status(db_session, agent.id).tries == 2
    refreshed = _status(db_session, parse.id)
    assert refreshed.status == TaskStatus.RUNNING
    assert refreshed.tries == 1
    assert refreshed.started_at.replace(tzinfo=None) == began.replace(tzinfo=None)


@pytest.mark.parametrize(
    'tries,expected',
    [
        (worker.MAX_RETRIES, TaskStatus.PENDING),  # one more attempt owed
        (worker.MAX_RETRIES + 1, TaskStatus.FAILED),  # that was the last
    ],
)
async def test_the_lease_timeout_abandons_only_after_the_last_attempt(
    db_session, make_task, cleared, not_shutting_down, monkeypatch, tries, expected
):
    """Same retry rule as the retry sweep: a FAILED row with tries <= MAX_RETRIES
    is revived, so retiring at that count to FAILED only detoured it through
    an "exhausted retries" message for 30 s."""
    task = make_task(TaskStatus.RUNNING, tries=tries)
    task.started_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        minutes=35
    )
    db_session.commit()

    async def no_run(task_id: int, attempt: int) -> None:
        return None

    monkeypatch.setattr(worker, 'execute_task', no_run)

    await worker.poll_and_schedule_tasks()

    refreshed = _status(db_session, task.id)
    if expected == TaskStatus.PENDING:
        assert cleared == [task.id]
        assert refreshed.status == TaskStatus.RUNNING  # retired, then started again
        assert refreshed.tries == tries + 1
    else:
        assert cleared == []
        assert refreshed.status == TaskStatus.FAILED
        assert refreshed.tries == tries
        assert 'max retries' in refreshed.error_message


async def test_the_lease_sweep_cancels_the_attempt_it_retires(
    db_session, make_task, cleared, not_shutting_down, monkeypatch
):
    """The retired coroutine is cancelled rather than left to run beside its
    retry; the retry then runs alone and records the outcome."""
    import asyncio

    task = make_task(TaskStatus.PENDING)
    calls: list[int] = []
    never = asyncio.Event()

    async def run(task_id: int) -> None:
        calls.append(task_id)
        if len(calls) == 1:
            await never.wait()  # attempt 1 would never return on its own

    monkeypatch.setitem(worker.TASK_HANDLERS, TYPE, run)

    await worker.poll_and_schedule_tasks()
    await asyncio.sleep(0)  # attempt 1 enters its handler and parks
    first = worker._attempts[(task.id, 1)]
    assert calls == [task.id]

    row = _status(db_session, task.id)
    row.started_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        minutes=35
    )
    db_session.commit()

    await worker.poll_and_schedule_tasks()  # retires attempt 1, starts attempt 2

    with pytest.raises(asyncio.CancelledError):
        await first
    await asyncio.wait_for(worker._attempts[(task.id, 2)], timeout=5)

    assert calls == [task.id, task.id]
    assert cleared == [task.id]
    refreshed = _status(db_session, task.id)
    assert refreshed.status == TaskStatus.COMPLETED
    assert refreshed.tries == 2
    await asyncio.sleep(0)  # done callbacks run on the next loop turn
    assert worker._attempts == {}  # both handles forgotten once done


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
