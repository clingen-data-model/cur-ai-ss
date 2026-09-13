"""started_at, and the durations it makes computable."""

import pytest

from lib.bin import worker
from lib.models import GeneDB, PaperDB, TaskDB
from lib.tasks.models import TaskStatus, TaskType

TYPE = TaskType.PDF_PARSING


@pytest.fixture
def queued_task(db_session):
    """A PENDING task, committed so the worker's own session can see it."""
    gene = GeneDB(symbol='BRCA1')
    db_session.add(gene)
    db_session.flush()
    paper = PaperDB(
        gene_id=gene.id, filename='p.pdf', content_hash='h', title='A paper'
    )
    db_session.add(paper)
    db_session.flush()
    task = TaskDB(paper_id=paper.id, type=TYPE, status=TaskStatus.PENDING)
    db_session.add(task)
    db_session.commit()
    return task


def _handler(monkeypatch, fail: bool = False):
    async def run(task_id: int) -> None:
        if fail:
            raise RuntimeError('boom')

    monkeypatch.setitem(worker.TASK_HANDLERS, TYPE, run)


async def test_started_at_is_stamped_when_the_task_runs(
    db_session, queued_task, monkeypatch
):
    assert queued_task.started_at is None
    _handler(monkeypatch)

    await worker.execute_task(queued_task.id)

    db_session.expire_all()
    task = db_session.get(TaskDB, queued_task.id)
    assert task.status == TaskStatus.COMPLETED
    assert task.started_at is not None
    # updated_at is the finish time, so the pair is a duration.
    assert task.updated_at >= task.started_at


async def test_started_at_is_stamped_even_when_the_task_fails(
    db_session, queued_task, monkeypatch
):
    """A failed run still took time; excluding it would bias estimates toward
    the cases that happened to succeed."""
    _handler(monkeypatch, fail=True)

    await worker.execute_task(queued_task.id)

    db_session.expire_all()
    task = db_session.get(TaskDB, queued_task.id)
    assert task.status == TaskStatus.FAILED
    assert task.started_at is not None


async def test_a_retry_restamps_started_at(db_session, queued_task, monkeypatch):
    """started_at must describe the attempt that produced the current status,
    not the first one ever made -- otherwise a retried task reports a duration
    spanning every attempt and the wait between them."""
    _handler(monkeypatch, fail=True)
    await worker.execute_task(queued_task.id)
    db_session.expire_all()
    first = db_session.get(TaskDB, queued_task.id).started_at

    db_session.get(TaskDB, queued_task.id).status = TaskStatus.PENDING
    db_session.commit()
    _handler(monkeypatch)
    await worker.execute_task(queued_task.id)

    db_session.expire_all()
    task = db_session.get(TaskDB, queued_task.id)
    assert task.started_at > first
    assert task.tries == 2


async def test_started_at_is_exposed_on_the_response_model(
    db_session, queued_task, monkeypatch
):
    from lib.tasks.models import TaskResp

    _handler(monkeypatch)
    await worker.execute_task(queued_task.id)

    db_session.expire_all()
    resp = TaskResp.model_validate(
        db_session.get(TaskDB, queued_task.id), from_attributes=True
    )
    assert resp.started_at is not None
