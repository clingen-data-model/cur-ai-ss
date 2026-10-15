"""The worker queues Extraction Verification once a paper has settled."""

import pytest

from lib.bin.worker import MAX_RETRIES, _maybe_queue_verification
from lib.models import GeneDB, PaperDB, TaskDB
from lib.tasks.models import TaskStatus, TaskType

VERIFY = TaskType.EXTRACTION_VERIFICATION


@pytest.fixture
def paper(db_session):
    gene = GeneDB(symbol='BRCA1')
    db_session.add(gene)
    db_session.flush()
    p = PaperDB(content_hash='abc123', gene_id=gene.id, filename='test.pdf')
    db_session.add(p)
    db_session.flush()
    return p


def _task(db_session, paper, status, task_type=TaskType.HPO_LINKING, tries=1):
    task = TaskDB(paper_id=paper.id, type=task_type, status=status, tries=tries)
    db_session.add(task)
    db_session.flush()
    return task


def _verifications(db_session, paper):
    return [
        (t.status, t.tries)
        for t in db_session.query(TaskDB).filter_by(paper_id=paper.id, type=VERIFY)
    ]


def test_queued_when_the_last_task_completes(db_session, paper):
    _task(db_session, paper, TaskStatus.COMPLETED, TaskType.VARIANT_ANNOTATION)
    last = _task(db_session, paper, TaskStatus.COMPLETED)

    _maybe_queue_verification(db_session, last)

    assert _verifications(db_session, paper) == [(TaskStatus.PENDING, 0)]


@pytest.mark.parametrize(
    'status', [TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING]
)
def test_not_queued_while_another_task_is_in_flight(db_session, paper, status):
    _task(db_session, paper, status, TaskType.PHENOTYPE_EXTRACTION)
    done = _task(db_session, paper, TaskStatus.COMPLETED)

    _maybe_queue_verification(db_session, done)

    assert _verifications(db_session, paper) == []


def test_not_queued_while_a_failure_is_owed_a_retry(db_session, paper):
    _task(
        db_session,
        paper,
        TaskStatus.FAILED,
        TaskType.PHENOTYPE_EXTRACTION,
        tries=MAX_RETRIES,
    )
    done = _task(db_session, paper, TaskStatus.COMPLETED)

    _maybe_queue_verification(db_session, done)

    assert _verifications(db_session, paper) == []


def test_a_final_failure_settles_the_paper_too(db_session, paper):
    """A pipeline that ends in a failure still gets its flags merged, as it
    still gets its snapshot."""
    _task(db_session, paper, TaskStatus.COMPLETED, TaskType.VARIANT_ANNOTATION)
    failed = _task(db_session, paper, TaskStatus.FAILED, tries=MAX_RETRIES + 1)

    _maybe_queue_verification(db_session, failed)

    assert _verifications(db_session, paper) == [(TaskStatus.PENDING, 0)]


def test_a_failure_with_retries_left_does_not(db_session, paper):
    failed = _task(db_session, paper, TaskStatus.FAILED, tries=MAX_RETRIES)

    _maybe_queue_verification(db_session, failed)

    assert _verifications(db_session, paper) == []


def test_verification_does_not_queue_itself(db_session, paper):
    _task(db_session, paper, TaskStatus.COMPLETED)
    verify = _task(db_session, paper, TaskStatus.COMPLETED, VERIFY)

    _maybe_queue_verification(db_session, verify)

    assert _verifications(db_session, paper) == [(TaskStatus.COMPLETED, 1)]


def test_an_earlier_verification_is_reset_when_the_paper_settles_again(
    db_session, paper
):
    """A re-run of one agent completes into an already-verified paper: the
    one verification row goes back to pending rather than a second appearing,
    and its own completed row does not count as in flight."""
    _task(db_session, paper, TaskStatus.COMPLETED, VERIFY, tries=1)
    rerun = _task(
        db_session, paper, TaskStatus.COMPLETED, TaskType.PATIENT_DEMOGRAPHICS
    )

    _maybe_queue_verification(db_session, rerun)

    assert _verifications(db_session, paper) == [(TaskStatus.PENDING, 0)]


def test_a_running_verification_is_left_alone(db_session, paper):
    _task(db_session, paper, TaskStatus.RUNNING, VERIFY)
    rerun = _task(db_session, paper, TaskStatus.COMPLETED)

    _maybe_queue_verification(db_session, rerun)

    assert _verifications(db_session, paper) == [(TaskStatus.RUNNING, 1)]
