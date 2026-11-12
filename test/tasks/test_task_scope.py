"""A task is queued only with a scope its step runs over, naming a row of its
own paper (check_task_scope, checked again inside enqueue_task)."""

import pytest

from lib.models import FamilyDB, GeneDB, PaperDB
from lib.tasks.misc import TaskScopeError, check_task_scope, enqueue_task
from lib.tasks.models import TaskDB, TaskType


def _paper(db_session, content_hash):
    gene = db_session.query(GeneDB).first()
    if gene is None:
        gene = GeneDB(symbol='BRCA1')
        db_session.add(gene)
        db_session.flush()
    paper = PaperDB(content_hash=content_hash, gene_id=gene.id, filename='p.pdf')
    db_session.add(paper)
    db_session.flush()
    return paper


def _family(db_session, paper, identifier='Family 1'):
    family = FamilyDB(
        paper_id=paper.id,
        identifier=identifier,
        identifier_evidence={'value': identifier, 'reasoning': 'test'},
        consanguinity=False,
        consanguinity_evidence={'value': False, 'reasoning': 'test'},
    )
    db_session.add(family)
    db_session.flush()
    return family


@pytest.fixture
def paper(db_session):
    return _paper(db_session, 'scope-a')


@pytest.fixture
def other_paper(db_session):
    return _paper(db_session, 'scope-b')


def test_a_row_of_this_paper_in_the_steps_own_column_is_queued(db_session, paper):
    family = _family(db_session, paper)

    check_task_scope(
        db_session,
        paper.id,
        TaskType.SEGREGATION_ANALYSIS_COMPUTED,
        family_id=family.id,
    )
    task = enqueue_task(
        db_session,
        paper_id=paper.id,
        task_type=TaskType.SEGREGATION_ANALYSIS_COMPUTED,
        family_id=family.id,
    )
    assert task.family_id == family.id


def test_no_id_is_allowed_for_paper_wide_and_per_row_steps(db_session, paper):
    # enqueue_all_instances queues one unscoped row of a per-row step when the
    # paper has none yet.
    check_task_scope(db_session, paper.id, TaskType.VARIANT_EXTRACTION)
    check_task_scope(db_session, paper.id, TaskType.SEGREGATION_ANALYSIS_COMPUTED)


def test_a_row_of_another_paper_is_refused(db_session, paper, other_paper):
    theirs = _family(db_session, other_paper)

    with pytest.raises(TaskScopeError) as caught:
        check_task_scope(
            db_session,
            paper.id,
            TaskType.SEGREGATION_ANALYSIS_COMPUTED,
            family_id=theirs.id,
        )
    assert caught.value.status_code == 404
    assert str(caught.value) == f'This paper has no family {theirs.id}'


def test_a_row_that_does_not_exist_is_refused(db_session, paper):
    with pytest.raises(TaskScopeError) as caught:
        check_task_scope(
            db_session, paper.id, TaskType.SEGREGATION_ANALYSIS_COMPUTED, family_id=999
        )
    assert caught.value.status_code == 404


def test_an_id_for_a_paper_wide_step_is_refused(db_session, paper):
    family = _family(db_session, paper)

    with pytest.raises(TaskScopeError) as caught:
        check_task_scope(
            db_session, paper.id, TaskType.VARIANT_EXTRACTION, family_id=family.id
        )
    assert caught.value.status_code == 400
    assert str(caught.value) == (
        '"Finding variants" runs once for the whole paper, not for one family'
    )


def test_an_id_in_another_column_is_refused(db_session, paper):
    family = _family(db_session, paper)

    with pytest.raises(TaskScopeError) as caught:
        check_task_scope(
            db_session, paper.id, TaskType.INDIVIDUAL_DEMOGRAPHICS, family_id=family.id
        )
    assert caught.value.status_code == 400
    assert str(caught.value) == (
        '"Filling in individual details" runs once per individual, so it takes '
        'an individual, not: family'
    )


def test_enqueue_task_checks_too_and_writes_nothing(db_session, paper, other_paper):
    theirs = _family(db_session, other_paper)

    with pytest.raises(TaskScopeError):
        enqueue_task(
            db_session,
            paper_id=paper.id,
            task_type=TaskType.SEGREGATION_ANALYSIS_COMPUTED,
            family_id=theirs.id,
        )
    assert db_session.query(TaskDB).count() == 0
