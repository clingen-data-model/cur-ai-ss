import pytest

from lib.bin.requeue_papers import (
    read_pmids,
    requeue_paper,
    resolve_papers,
    snapshot_paper,
)
from lib.models import GeneDB, PaperDB, SnapshotDB
from lib.tasks.models import TaskDB, TaskStatus, TaskType


@pytest.fixture
def gene(db_session):
    gene = GeneDB(symbol='BRCA1')
    db_session.add(gene)
    db_session.flush()
    return gene


def _paper(db_session, gene, content_hash, pmid=None):
    paper = PaperDB(
        content_hash=content_hash, gene_id=gene.id, filename='p.pdf', pmid=pmid
    )
    db_session.add(paper)
    db_session.flush()
    return paper


def _task(db_session, paper, task_type, status=TaskStatus.COMPLETED):
    task = TaskDB(paper_id=paper.id, type=task_type, status=status)
    db_session.add(task)
    db_session.flush()
    return task


def test_read_pmids_skips_blank_rows_and_strips(tmp_path):
    csv_path = tmp_path / 'papers.csv'
    csv_path.write_text('PMID,Year\n 111 ,2020\n,2021\n222,2022\n')

    assert read_pmids(csv_path) == ['111', '222']


def test_resolve_papers_reports_unmatched_pmids(db_session, gene):
    a = _paper(db_session, gene, 'a', pmid='111')
    b = _paper(db_session, gene, 'b')

    ids, missing = resolve_papers(db_session, ['111', '999'], [b.id])

    assert ids == sorted([a.id, b.id])
    assert missing == ['999']


def test_resolve_papers_rejects_an_unknown_paper_id(db_session):
    with pytest.raises(SystemExit):
        resolve_papers(db_session, [], [12345])


def test_requeue_resets_the_start_task_and_clears_stale_downstream_rows(
    db_session, gene
):
    paper = _paper(db_session, gene, 'a')
    start = _task(db_session, paper, TaskType.PAPER_CLASSIFIER)
    _task(db_session, paper, TaskType.PATIENT_EXTRACTION)
    _task(db_session, paper, TaskType.HPO_LINKING)

    reason = requeue_paper(db_session, paper.id, TaskType.PAPER_CLASSIFIER, 'test')

    assert reason is None
    db_session.refresh(start)
    assert start.status == TaskStatus.PENDING
    remaining = {t.type for t in db_session.query(TaskDB).all()}
    assert remaining == {TaskType.PAPER_CLASSIFIER}


def test_requeue_snapshots_the_paper_first(db_session, gene):
    paper = _paper(db_session, gene, 'a')
    _task(db_session, paper, TaskType.PAPER_CLASSIFIER)

    requeue_paper(db_session, paper.id, TaskType.PAPER_CLASSIFIER, 'Before re-running')

    snapshots = db_session.query(SnapshotDB).filter_by(paper_id=paper.id).all()
    assert [s.description for s in snapshots] == ['Before re-running']


@pytest.mark.parametrize('status', [TaskStatus.RUNNING, TaskStatus.QUEUED])
def test_a_busy_paper_is_skipped_untouched(db_session, gene, status):
    paper = _paper(db_session, gene, 'a')
    _task(db_session, paper, TaskType.PAPER_CLASSIFIER, status=TaskStatus.COMPLETED)
    live = _task(db_session, paper, TaskType.PATIENT_EXTRACTION, status=status)

    reason = requeue_paper(db_session, paper.id, TaskType.PAPER_CLASSIFIER, 'test')

    assert reason is not None
    assert db_session.get(TaskDB, live.id) is not None
    assert db_session.query(SnapshotDB).count() == 0
    classifier = (
        db_session.query(TaskDB).filter_by(type=TaskType.PAPER_CLASSIFIER).one()
    )
    assert classifier.status == TaskStatus.COMPLETED


def test_snapshot_only_queues_nothing(db_session, gene):
    paper = _paper(db_session, gene, 'a')
    done = _task(db_session, paper, TaskType.PAPER_CLASSIFIER)
    _task(db_session, paper, TaskType.PATIENT_EXTRACTION)

    assert snapshot_paper(db_session, paper.id, 'Baseline') is None

    assert db_session.query(SnapshotDB).filter_by(paper_id=paper.id).count() == 1
    assert db_session.query(TaskDB).count() == 2
    db_session.refresh(done)
    assert done.status == TaskStatus.COMPLETED
