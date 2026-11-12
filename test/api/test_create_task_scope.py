"""POST /papers/{id}/tasks refuses a scope its step cannot run over, or a row
of another paper, before the re-run's snapshot and clean-up."""

from lib.models import FamilyDB, GeneDB, PaperDB
from lib.models.snapshot import SnapshotDB
from lib.tasks.models import TaskDB


def _paper(db_session, content_hash):
    gene = db_session.query(GeneDB).first()
    if gene is None:
        gene = GeneDB(symbol='BRCA1')
        db_session.add(gene)
        db_session.flush()
    paper = PaperDB(content_hash=content_hash, gene_id=gene.id, filename='p.pdf')
    db_session.add(paper)
    db_session.commit()
    return paper


def _family(db_session, paper):
    family = FamilyDB(
        paper_id=paper.id,
        identifier='Family 1',
        identifier_evidence={'value': 'Family 1', 'reasoning': 'test'},
        consanguinity=False,
        consanguinity_evidence={'value': False, 'reasoning': 'test'},
    )
    db_session.add(family)
    db_session.commit()
    return family


def test_a_row_of_another_paper_is_refused_with_nothing_changed(client, db_session):
    paper = _paper(db_session, 'api-scope-a')
    theirs = _family(db_session, _paper(db_session, 'api-scope-b'))

    resp = client.post(
        f'/papers/{paper.id}/tasks',
        json={'type': 'Segregation Analysis Computed', 'family_id': theirs.id},
    )

    assert resp.status_code == 404
    assert resp.json()['detail'] == f'This paper has no family {theirs.id}'
    assert db_session.query(TaskDB).count() == 0
    assert db_session.query(SnapshotDB).count() == 0


def test_an_id_the_step_does_not_take_is_refused(client, db_session):
    paper = _paper(db_session, 'api-scope-c')
    family = _family(db_session, paper)

    resp = client.post(
        f'/papers/{paper.id}/tasks',
        json={'type': 'Variant Extraction', 'family_id': family.id},
    )

    assert resp.status_code == 400
    assert db_session.query(TaskDB).count() == 0


def test_a_row_of_this_paper_is_queued(client, db_session):
    paper = _paper(db_session, 'api-scope-d')
    family = _family(db_session, paper)

    resp = client.post(
        f'/papers/{paper.id}/tasks',
        json={'type': 'Segregation Analysis Computed', 'family_id': family.id},
    )

    assert resp.status_code == 200
    assert [t['family_id'] for t in resp.json()] == [family.id]
