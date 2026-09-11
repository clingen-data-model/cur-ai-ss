"""The re-run gate: a previous run's COMPLETED rows must not satisfy this run."""

import pytest

from lib.models import GeneDB, PaperDB
from lib.tasks.misc import (
    _patient_demographics_ready,
    _task_completed,
    invalidate_descendants,
)
from lib.tasks.models import TaskDB, TaskStatus, TaskType


@pytest.fixture
def paper(db_session):
    gene = GeneDB(symbol='BRCA1')
    db_session.add(gene)
    db_session.flush()
    p = PaperDB(content_hash='abc123', gene_id=gene.id, filename='test.pdf')
    db_session.add(p)
    db_session.flush()
    return p


def _task(db_session, paper, task_type, status=TaskStatus.COMPLETED, **kw):
    t = TaskDB(paper_id=paper.id, type=task_type, status=status, **kw)
    db_session.add(t)
    db_session.flush()
    return t


def test_clears_completed_descendants(db_session, paper):
    _task(db_session, paper, TaskType.PAPER_CLASSIFIER)
    _task(db_session, paper, TaskType.PATIENT_EXTRACTION)
    _task(db_session, paper, TaskType.VARIANT_EXTRACTION)
    _task(db_session, paper, TaskType.HPO_LINKING)

    removed = invalidate_descendants(db_session, paper.id, TaskType.PAPER_CLASSIFIER)

    assert removed == 3
    remaining = {t.type for t in db_session.query(TaskDB).all()}
    assert remaining == {TaskType.PAPER_CLASSIFIER}


def test_leaves_the_requeued_type_alone(db_session, paper):
    """enqueue_all_instances resets that row; deleting it here would drop the
    attribution and history it is about to rewrite."""
    own = _task(db_session, paper, TaskType.PAPER_CLASSIFIER)

    invalidate_descendants(db_session, paper.id, TaskType.PAPER_CLASSIFIER)

    assert db_session.get(TaskDB, own.id) is not None


@pytest.mark.parametrize('status', [TaskStatus.RUNNING, TaskStatus.QUEUED])
def test_spares_in_flight_rows(db_session, paper, status):
    """A handler is mid-flight against these; deleting the row out from under it
    relocates the failure rather than removing it."""
    live = _task(db_session, paper, TaskType.PATIENT_EXTRACTION, status=status)

    removed = invalidate_descendants(db_session, paper.id, TaskType.PAPER_CLASSIFIER)

    assert removed == 0
    assert db_session.get(TaskDB, live.id) is not None


def test_does_not_touch_other_papers(db_session, paper):
    gene = db_session.query(GeneDB).first()
    other = PaperDB(content_hash='def456', gene_id=gene.id, filename='other.pdf')
    db_session.add(other)
    db_session.flush()
    theirs = _task(db_session, other, TaskType.PATIENT_EXTRACTION)

    invalidate_descendants(db_session, paper.id, TaskType.PAPER_CLASSIFIER)

    assert db_session.get(TaskDB, theirs.id) is not None


def test_terminal_task_has_no_descendants(db_session, paper):
    _task(db_session, paper, TaskType.HPO_LINKING)

    assert invalidate_descendants(db_session, paper.id, TaskType.HPO_LINKING) == 0


def test_closes_the_patient_variant_occurrence_race(db_session, paper):
    """The actual bug, in the order it happened on paper 27.

    PATIENT_EXTRACTION sits behind the slow PEDIGREE_DESCRIPTION, so when the
    fast VARIANT_EXTRACTION finishes it asks the gate whether patients are
    ready -- and the *previous* run's COMPLETED rows say yes. That enqueues
    PATIENT_VARIANT_OCCURRENCES against a patient set PATIENT_EXTRACTION is
    about to delete and rebuild, and its INSERT dies on a foreign key.
    """
    _task(db_session, paper, TaskType.PAPER_CLASSIFIER)
    _task(db_session, paper, TaskType.PATIENT_EXTRACTION)  # stale, previous run

    # Before the fix the stale row satisfies the gate.
    assert _task_completed(db_session, paper.id, TaskType.PATIENT_EXTRACTION)
    assert _patient_demographics_ready(db_session, paper.id)

    invalidate_descendants(db_session, paper.id, TaskType.PAPER_CLASSIFIER)

    # After it, the gate holds until this run's PATIENT_EXTRACTION actually runs.
    assert not _task_completed(db_session, paper.id, TaskType.PATIENT_EXTRACTION)
    assert not _patient_demographics_ready(db_session, paper.id)
