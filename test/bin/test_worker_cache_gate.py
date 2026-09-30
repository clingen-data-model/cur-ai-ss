"""The per-(paper, task type) fan-out gate: the first task of a batch runs
alone so its request writes the prompt-cache entry before the rest start."""

import asyncio

import pytest

from lib.bin import worker
from lib.tasks.models import TaskType

TYPE = TaskType.PATIENT_DEMOGRAPHICS


@pytest.fixture
def fresh_gates(monkeypatch):
    monkeypatch.setattr(worker, '_fanout_gates', {})
    monkeypatch.setattr(worker, '_warm_until', {})


@pytest.fixture
def recorder(monkeypatch):
    """A fake execute_task that records when each task starts and finishes,
    on a virtual clock (asyncio.sleep is real but short)."""
    events: list[tuple[str, int]] = []

    async def fake_execute(task_id: int) -> None:
        events.append(('start', task_id))
        await asyncio.sleep(0.02)
        events.append(('end', task_id))

    monkeypatch.setattr(worker, 'execute_task', fake_execute)
    return events


def _run_batch(task_ids, paper_id=1, task_type=TYPE):
    sem = asyncio.Semaphore(30)
    return asyncio.gather(
        *(
            worker.execute_task_with_semaphore(
                t, sem, sem, paper_id=paper_id, task_type=task_type
            )
            for t in task_ids
        )
    )


async def test_first_task_finishes_before_the_others_start(fresh_gates, recorder):
    await _run_batch([1, 2, 3])

    assert recorder[:2] == [('start', 1), ('end', 1)]
    later = recorder[2:]
    # 2 and 3 both start before either ends: they ran together.
    assert [e for e, _ in later] == ['start', 'start', 'end', 'end']


async def test_a_warm_gate_lets_a_later_task_start_at_once(fresh_gates, recorder):
    await _run_batch([1, 2])
    recorder.clear()

    await _run_batch([3, 4])

    assert [e for e, _ in recorder] == ['start', 'start', 'end', 'end']


async def test_an_expired_window_serialises_the_first_task_again(
    fresh_gates, recorder, monkeypatch
):
    await _run_batch([1])
    worker._warm_until[(1, TYPE)] = 0.0  # window long gone
    recorder.clear()

    await _run_batch([2, 3])

    assert recorder[:2] == [('start', 2), ('end', 2)]


async def test_other_papers_and_types_are_not_held(fresh_gates, recorder):
    await asyncio.gather(_run_batch([1, 2], paper_id=1), _run_batch([3, 4], paper_id=2))

    starts = [t for e, t in recorder if e == 'start']
    # Each paper's first task (1 and 3) starts before that paper's second, but
    # the two papers interleave: 3 is not waiting on 1.
    assert starts.index(1) < starts.index(2)
    assert starts.index(3) < starts.index(4)
    assert starts[:2] == [1, 3]


async def test_a_failing_first_task_still_opens_the_gate(fresh_gates, monkeypatch):
    calls = []

    async def fake_execute(task_id: int) -> None:
        calls.append(task_id)
        if task_id == 1:
            raise RuntimeError('provider down')

    monkeypatch.setattr(worker, 'execute_task', fake_execute)

    results = await asyncio.gather(_run_batch([1, 2, 3]), return_exceptions=True)

    assert isinstance(results[0], RuntimeError)
    assert calls == [1, 2, 3]
    assert worker._gate_is_warm((1, TYPE))


async def test_no_paper_means_no_gate(fresh_gates, recorder):
    sem = asyncio.Semaphore(30)
    await asyncio.gather(
        worker.execute_task_with_semaphore(1, sem, sem),
        worker.execute_task_with_semaphore(2, sem, sem),
    )

    assert [e for e, _ in recorder] == ['start', 'start', 'end', 'end']
    assert worker._fanout_gates == {}
