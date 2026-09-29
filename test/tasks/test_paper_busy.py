"""Re-running and restoring are refused while a paper has tasks in flight."""

import pytest

from lib.models import GeneDB, PaperDB
from lib.tasks.misc import paper_busy_message
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


def _task(db_session, paper, task_type, status, **kw):
    db_session.add(TaskDB(paper_id=paper.id, type=task_type, status=status, **kw))
    db_session.flush()


def test_idle_paper_is_not_busy(db_session, paper):
    _task(db_session, paper, TaskType.PDF_PARSING, TaskStatus.COMPLETED)
    _task(db_session, paper, TaskType.PAPER_MONDO_LINKING, TaskStatus.FAILED)

    assert paper_busy_message(db_session, paper.id, 're-running') is None


@pytest.mark.parametrize(
    'status', [TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING]
)
def test_any_active_status_is_busy(db_session, paper, status):
    _task(db_session, paper, TaskType.PDF_PARSING, status)

    assert paper_busy_message(db_session, paper.id, 're-running') == (
        '1 task still pending or running (PDF Parsing). '
        'Wait for it to finish before re-running.'
    )


def test_message_counts_by_type_most_first(db_session, paper):
    for _ in range(3):
        _task(db_session, paper, TaskType.HPO_LINKING, TaskStatus.RUNNING)
    _task(db_session, paper, TaskType.PAPER_MONDO_LINKING, TaskStatus.PENDING)

    assert paper_busy_message(db_session, paper.id, 'restoring a snapshot') == (
        '4 tasks still pending or running (HPO Linking ×3, Paper MONDO Linking). '
        'Wait for them to finish before restoring a snapshot.'
    )


def test_other_papers_do_not_count(db_session, paper):
    gene = db_session.query(GeneDB).first()
    other = PaperDB(content_hash='def456', gene_id=gene.id, filename='other.pdf')
    db_session.add(other)
    db_session.flush()
    _task(db_session, other, TaskType.PDF_PARSING, TaskStatus.RUNNING)

    assert paper_busy_message(db_session, paper.id, 're-running') is None
