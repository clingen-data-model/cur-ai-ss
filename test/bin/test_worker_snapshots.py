"""The worker's completion snapshot waits until nothing is in flight."""

import pytest

from lib.bin.worker import MAX_RETRIES, _maybe_write_snapshot
from lib.models import GeneDB, PaperDB, TaskDB
from lib.tasks.models import TaskStatus, TaskType


@pytest.fixture
def written(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(
        'lib.bin.worker.write_snapshot_safe',
        lambda session, paper_id, **kw: calls.append(paper_id),
    )
    return calls


@pytest.fixture
def paper(db_session):
    gene = GeneDB(symbol='BRCA1')
    db_session.add(gene)
    db_session.flush()
    p = PaperDB(content_hash='abc123', gene_id=gene.id, filename='test.pdf')
    db_session.add(p)
    db_session.flush()
    return p


def _task(db_session, paper, status, tries=1):
    db_session.add(
        TaskDB(paper_id=paper.id, type=TaskType.PDF_PARSING, status=status, tries=tries)
    )
    db_session.flush()


def test_snapshots_when_every_task_completed(db_session, paper, written):
    _task(db_session, paper, TaskStatus.COMPLETED)

    _maybe_write_snapshot(db_session, paper.id)

    assert written == [paper.id]


def test_snapshots_when_a_failure_is_final(db_session, paper, written):
    """Paper 20 never got a completion snapshot: one MONDO task failed for good."""
    _task(db_session, paper, TaskStatus.COMPLETED)
    _task(db_session, paper, TaskStatus.FAILED, tries=MAX_RETRIES + 1)

    _maybe_write_snapshot(db_session, paper.id)

    assert written == [paper.id]


@pytest.mark.parametrize(
    'status', [TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING]
)
def test_skips_while_a_task_is_active(db_session, paper, written, status):
    _task(db_session, paper, TaskStatus.COMPLETED)
    _task(db_session, paper, status)

    _maybe_write_snapshot(db_session, paper.id)

    assert written == []


def test_skips_while_a_failure_is_still_owed_a_retry(db_session, paper, written):
    """Restoring a snapshot holding this would have the worker retry it."""
    _task(db_session, paper, TaskStatus.COMPLETED)
    _task(db_session, paper, TaskStatus.FAILED, tries=MAX_RETRIES)

    _maybe_write_snapshot(db_session, paper.id)

    assert written == []
