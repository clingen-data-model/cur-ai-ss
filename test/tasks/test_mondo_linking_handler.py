"""The MONDO linking task on a paper (or occurrence) with no disease name."""

import pytest

from lib.models import GeneDB, PaperDB, TaskDB
from lib.models.flag import FlagDB
from lib.tasks.handlers import handle_mondo_linking
from lib.tasks.models import TaskStatus, TaskType


@pytest.fixture
def paper_without_disease(db_session):
    gene = GeneDB(symbol='RB1')
    db_session.add(gene)
    db_session.flush()
    paper = PaperDB(
        gene_id=gene.id,
        filename='rb1.pdf',
        content_hash='hash-rb1',
        title='A paper with no disease name',
        disease_name=None,
        mondo_id='MONDO:0000001',
        mondo_term='stale term',
    )
    db_session.add(paper)
    db_session.flush()
    task = TaskDB(
        paper_id=paper.id,
        type=TaskType.PAPER_MONDO_LINKING,
        status=TaskStatus.RUNNING,
    )
    db_session.add(task)
    db_session.add(
        FlagDB(
            paper_id=paper.id,
            source=TaskType.PAPER_MONDO_LINKING.name,
            kind='ambiguous',
            subject='left by an earlier run that had a disease name',
            evidence={},
        )
    )
    # The handler opens its own session on the same engine, so the seed rows
    # have to be committed for it to see them.
    db_session.commit()
    return paper, task


async def test_no_disease_name_completes_and_clears_the_link(
    db_session, paper_without_disease
):
    """Paper 105 (RB1, 2026-10-19) came out of the metadata pass with no
    disease name; the handler skipped the agent and then read the agent's
    result for the flags -- UnboundLocalError on every attempt."""
    paper, task = paper_without_disease

    await handle_mondo_linking(task.id)

    db_session.expire_all()
    paper = db_session.get(PaperDB, paper.id)
    assert paper.mondo_id is None
    assert paper.mondo_term is None
    assert paper.mondo_match_context is None
    assert (
        db_session.query(FlagDB)
        .filter(
            FlagDB.paper_id == paper.id,
            FlagDB.source == TaskType.PAPER_MONDO_LINKING.name,
        )
        .count()
        == 0
    )
