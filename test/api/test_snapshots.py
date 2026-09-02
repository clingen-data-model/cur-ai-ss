import json

import pytest

from lib.bin.worker import _maybe_write_snapshot
from lib.misc.pdf.paths import snapshots_dir
from lib.misc.snapshots import (
    InvalidSnapshotNameError,
    SnapshotIncompatibleError,
    list_snapshots,
    restore_snapshot,
    snapshot_path,
    write_snapshot,
)
from lib.models import (
    AnnotatedVariantDB,
    Base,
    ConversationDB,
    FamilyDB,
    GeneDB,
    HarmonizedVariantDB,
    HpoDB,
    PaperDB,
    PatientDB,
    PatientVariantOccurrenceDB,
    PedigreeDB,
    PhenotypeDB,
    SegregationAnalysisComputedDB,
    SegregationEvidenceDB,
    TaskDB,
    VariantDB,
)
from lib.models.patient import AgeUnit
from lib.tasks.models import TaskStatus, TaskType


def test_snapshot_covers_every_paper_scoped_table():
    """Guard: a new table reachable from papers via FKs must be added to the
    snapshot (lib.misc.snapshots._INSERT_ORDER) or to the exclusions below."""
    from lib.misc.snapshots import _INSERT_ORDER

    # Deliberately not snapshotted: tasks are preserved through a reset,
    # conversations are chat history the user keeps.
    excluded = {'tasks', 'conversations'}
    snapshotted = {model.__table__.name for _, model in _INSERT_ORDER} | {'papers'}

    reachable = {'papers'}
    changed = True
    while changed:
        changed = False
        for table in Base.metadata.tables.values():
            if table.name in reachable:
                continue
            for fk in table.foreign_keys:
                if fk.column.table.name in reachable:
                    reachable.add(table.name)
                    changed = True
                    break

    missing = reachable - snapshotted - excluded
    assert not missing, (
        f'Paper-scoped tables missing from snapshot: {sorted(missing)}. '
        f'Add them to _INSERT_ORDER (and the restore delete order) or to the '
        f'exclusions in this test.'
    )


def _ev(value: object = None) -> dict:
    d: dict = {'value': value, 'reasoning': 'test'}
    if value is not None:
        d['quote'] = 'test quote'
    return d


def _patient_fields(identifier: str) -> dict:
    return dict(
        identifier=identifier,
        proband_status='Unknown',
        sex='Unknown',
        country_of_origin='Unknown',
        race='Unknown',
        ethnicity='Unknown',
        affected_status='Unknown',
        identifier_evidence=_ev(identifier),
        proband_status_evidence=_ev('Unknown'),
        sex_evidence=_ev('Unknown'),
        age_diagnosis_evidence=_ev(),
        age_report_evidence=_ev(),
        age_death_evidence=_ev(),
        country_of_origin_evidence=_ev('Unknown'),
        race_evidence=_ev('Unknown'),
        ethnicity_evidence=_ev('Unknown'),
        affected_status_evidence=_ev('Unknown'),
        family_assignment_evidence=_ev('Family 1'),
    )


def _variant_fields(hgvs_c: str) -> dict:
    return dict(
        variant=hgvs_c,
        transcript='NM_007294.3',
        genome_build='GRCh38',
        hgvs_c=hgvs_c,
        variant_type='Missense',
        functional_evidence=False,
        main_focus=False,
        transcript_evidence=_ev('NM_007294.3'),
        protein_accession_evidence=_ev(),
        genomic_accession_evidence=_ev(),
        lrg_accession_evidence=_ev(),
        gene_accession_evidence=_ev(),
        genomic_coordinates_evidence=_ev(),
        genome_build_evidence=_ev('GRCh38'),
        rsid_evidence=_ev(),
        caid_evidence=_ev(),
        variant_evidence=_ev(hgvs_c),
        hgvs_c_evidence=_ev(hgvs_c),
        hgvs_p_evidence=_ev(),
        hgvs_g_evidence=_ev(),
        variant_type_evidence=_ev('Missense'),
        functional_evidence_evidence=_ev(False),
        main_focus_evidence=_ev(False),
    )


@pytest.fixture
def snapshot_paper(db_session, agent_run):
    """A paper with a full domain graph across every snapshotted table."""
    gene = GeneDB(symbol='TP53')
    db_session.add(gene)
    db_session.flush()
    paper = PaperDB(
        content_hash='snapshot-test-hash',
        gene_id=gene.id,
        filename='test.pdf',
        title='Original Title',
        disease_name='Original disease',
        disease_name_evidence=_ev('Original disease'),
    )
    db_session.add(paper)
    db_session.flush()
    family = FamilyDB(
        paper_id=paper.id,
        agent_run_id=agent_run.id,
        identifier='Family 1',
        identifier_evidence=_ev('Family 1'),
        consanguinity=False,
        consanguinity_evidence=_ev(False),
    )
    db_session.add(family)
    db_session.flush()
    p1 = PatientDB(
        paper_id=paper.id,
        family_id=family.id,
        agent_run_id=agent_run.id,
        age_diagnosis=5,
        age_diagnosis_unit=AgeUnit.Years,
        **_patient_fields('P1'),
    )
    p2 = PatientDB(
        paper_id=paper.id,
        family_id=family.id,
        agent_run_id=agent_run.id,
        **_patient_fields('P2'),
    )
    db_session.add_all([p1, p2])
    db_session.flush()
    db_session.add(PedigreeDB(paper_id=paper.id, image_id=1, description='pedigree'))
    phenotype = PhenotypeDB(
        paper_id=paper.id,
        patient_id=p1.id,
        concept='seizures',
        concept_evidence=_ev('seizures'),
    )
    db_session.add(phenotype)
    db_session.flush()
    db_session.add(
        HpoDB(
            phenotype_id=phenotype.id,
            hpo_id='HP:0001250',
            hpo_name='Seizure',
            reasoning='match',
        )
    )
    v1 = VariantDB(
        paper_id=paper.id, agent_run_id=agent_run.id, **_variant_fields('c.1A>G')
    )
    v2 = VariantDB(
        paper_id=paper.id, agent_run_id=agent_run.id, **_variant_fields('c.2T>C')
    )
    db_session.add_all([v1, v2])
    db_session.flush()
    db_session.add(
        HarmonizedVariantDB(
            variant_id=v1.id,
            gnomad_style_coordinates='17:1:A:G',
            hgvs_c='c.1A>G',
            reasoning='harmonized',
        )
    )
    db_session.add(AnnotatedVariantDB(variant_id=v1.id, pathogenicity='Pathogenic'))
    pvo_fields = dict(
        zygosity='Heterozygous',
        zygosity_evidence=_ev('Heterozygous'),
        inheritance='Dominant',
        inheritance_evidence=_ev('Dominant'),
        de_novo=False,
        de_novo_evidence=_ev(False),
        testing_methods=['Sanger Sequencing'],
        testing_methods_evidence=[_ev('Sanger Sequencing')],
    )
    pvo1 = PatientVariantOccurrenceDB(
        paper_id=paper.id, patient_id=p1.id, variant_id=v1.id, **pvo_fields
    )
    pvo2 = PatientVariantOccurrenceDB(
        paper_id=paper.id, patient_id=p1.id, variant_id=v2.id, **pvo_fields
    )
    db_session.add_all([pvo1, pvo2])
    db_session.flush()
    pvo1.paired_variant_link_id = pvo2.id
    pvo2.paired_variant_link_id = pvo1.id
    db_session.add(
        SegregationEvidenceDB(
            family_id=family.id,
            has_unexplainable_non_segregations=False,
            has_unexplainable_non_segregations_evidence=_ev(False),
        )
    )
    db_session.add(
        SegregationAnalysisComputedDB(
            family_id=family.id,
            segregation_count=2,
            segregation_count_reasoning=_ev(2),
            affected_count=1,
            affected_count_reasoning=_ev(1),
            unaffected_count=1,
            unaffected_count_reasoning=_ev(1),
            computed_lod_score=0.6,
            computed_lod_score_reasoning=_ev(0.6),
            points_assigned=0.5,
            points_assigned_reasoning=_ev(0.5),
            meets_minimum_criteria=False,
            meets_minimum_criteria_reasoning=_ev(False),
        )
    )
    paper_task = TaskDB(
        paper_id=paper.id,
        agent_run_id=agent_run.id,
        type=TaskType.PDF_PARSING,
        status=TaskStatus.COMPLETED,
    )
    scoped_task = TaskDB(
        paper_id=paper.id,
        agent_run_id=agent_run.id,
        type=TaskType.PATIENT_DEMOGRAPHICS,
        status=TaskStatus.COMPLETED,
        patient_id=p1.id,
    )
    db_session.add_all([paper_task, scoped_task])
    db_session.add(
        ConversationDB(
            paper_id=paper.id,
            conversation_id='conv-1',
            messages=[{'role': 'user', 'content': 'hi'}],
        )
    )
    db_session.flush()
    return {
        'paper': paper,
        'family': family,
        'p1': p1,
        'p2': p2,
        'phenotype': phenotype,
        'v1': v1,
        'v2': v2,
        'pvo1': pvo1,
        'pvo2': pvo2,
        'paper_task': paper_task,
        'scoped_task': scoped_task,
        'agent_run': agent_run,
    }


def test_reset_roundtrip(client, db_session, test_user, snapshot_paper):
    paper = snapshot_paper['paper']
    path = write_snapshot(paper.id, db_session)
    assert path is not None and path.exists()
    name = path.name

    # Mutate everything a user or rerun could touch.
    p1 = snapshot_paper['p1']
    p1.identifier = 'EDITED'
    p1.age_diagnosis_unit = AgeUnit.Months
    paper.title = 'Edited Title'
    paper.disease_name = 'Edited disease'
    db_session.delete(snapshot_paper['pvo1'])
    db_session.query(HpoDB).delete()
    db_session.query(AnnotatedVariantDB).delete()
    db_session.flush()
    new_patient = PatientDB(
        paper_id=paper.id,
        family_id=snapshot_paper['family'].id,
        agent_run_id=snapshot_paper['agent_run'].id,
        **_patient_fields('P-new'),
    )
    db_session.add(new_patient)
    db_session.flush()
    new_scoped_task = TaskDB(
        paper_id=paper.id,
        agent_run_id=snapshot_paper['agent_run'].id,
        type=TaskType.PHENOTYPE_EXTRACTION,
        status=TaskStatus.COMPLETED,
        patient_id=new_patient.id,
    )
    db_session.add(new_scoped_task)
    db_session.flush()

    response = client.post(f'/papers/{paper.id}/reset', json={'snapshot_name': name})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['title'] == 'Original Title'
    assert body['disease_name'] == 'Original disease'
    assert body['updated_by_user_id'] == test_user.id
    assert body['content_hash'] == 'snapshot-test-hash'

    patients = db_session.query(PatientDB).filter_by(paper_id=paper.id).all()
    assert sorted(p.identifier for p in patients) == ['P1', 'P2']
    restored_p1 = next(p for p in patients if p.identifier == 'P1')
    assert restored_p1.id == snapshot_paper['p1'].id  # PK preserved
    assert restored_p1.age_diagnosis_unit == AgeUnit.Years  # enum round-trip
    assert db_session.query(HpoDB).count() == 1
    assert db_session.query(AnnotatedVariantDB).count() == 1
    pvos = db_session.query(PatientVariantOccurrenceDB).all()
    assert len(pvos) == 2
    by_id = {o.id: o for o in pvos}
    assert (
        by_id[snapshot_paper['pvo1'].id].paired_variant_link_id
        == snapshot_paper['pvo2'].id
    )
    assert (
        by_id[snapshot_paper['pvo2'].id].paired_variant_link_id
        == snapshot_paper['pvo1'].id
    )
    assert db_session.query(SegregationEvidenceDB).count() == 1
    assert db_session.query(SegregationAnalysisComputedDB).count() == 1
    assert db_session.query(PedigreeDB).count() == 1

    # Task history: pre-snapshot tasks survive with scope intact; the task
    # scoped to the post-snapshot patient is gone.
    tasks = db_session.query(TaskDB).filter_by(paper_id=paper.id).all()
    types = {t.type for t in tasks}
    assert TaskType.PDF_PARSING in types
    scoped = next(t for t in tasks if t.type == TaskType.PATIENT_DEMOGRAPHICS)
    assert scoped.patient_id == snapshot_paper['p1'].id
    assert TaskType.PHENOTYPE_EXTRACTION not in types

    # Conversation untouched.
    assert db_session.query(ConversationDB).filter_by(paper_id=paper.id).count() == 1


def test_write_snapshot_idempotent(db_session, snapshot_paper):
    paper = snapshot_paper['paper']
    assert write_snapshot(paper.id, db_session) is not None
    assert write_snapshot(paper.id, db_session) is None
    assert len(list_snapshots(paper.id)) == 1

    snapshot_paper['p1'].identifier = 'CHANGED'
    db_session.flush()
    assert write_snapshot(paper.id, db_session) is not None
    snapshots = list_snapshots(paper.id)
    assert len(snapshots) == 2
    # Newest first, and metadata carries the agent run info.
    assert snapshots[0].created_at >= snapshots[1].created_at
    assert snapshots[0].model == snapshot_paper['agent_run'].model
    assert snapshots[0].git_hash == snapshot_paper['agent_run'].git_hash


def test_list_snapshots_endpoint(client, db_session, snapshot_paper):
    paper = snapshot_paper['paper']
    response = client.get(f'/papers/{paper.id}/snapshots')
    assert response.status_code == 200
    assert response.json() == []

    write_snapshot(paper.id, db_session)
    response = client.get(f'/papers/{paper.id}/snapshots')
    assert response.status_code == 200
    (meta,) = response.json()
    assert meta['paper_id'] == paper.id
    assert meta['name'].startswith('extraction_')

    assert client.get('/papers/999999/snapshots').status_code == 404


def test_reset_guards(client, db_session, snapshot_paper):
    paper = snapshot_paper['paper']
    assert (
        client.post('/papers/999999/reset', json={'snapshot_name': 'x'}).status_code
        == 404
    )
    # Path traversal / malformed names are rejected.
    response = client.post(
        f'/papers/{paper.id}/reset', json={'snapshot_name': '../../etc/passwd'}
    )
    assert response.status_code == 400
    # Well-formed name that doesn't exist.
    response = client.post(
        f'/papers/{paper.id}/reset',
        json={'snapshot_name': 'extraction_20260101T000000000000Z.json'},
    )
    assert response.status_code == 404
    # Active task blocks reset.
    write_snapshot(paper.id, db_session)
    name = list_snapshots(paper.id)[0].name
    snapshot_paper['paper_task'].status = TaskStatus.RUNNING
    db_session.flush()
    response = client.post(f'/papers/{paper.id}/reset', json={'snapshot_name': name})
    assert response.status_code == 409


def test_snapshot_name_validation():
    with pytest.raises(InvalidSnapshotNameError):
        snapshot_path(1, '../escape.json')
    with pytest.raises(InvalidSnapshotNameError):
        snapshot_path(1, 'extraction_bogus.json')


def test_schema_drift_tolerated_and_guarded(db_session, test_user, snapshot_paper):
    paper = snapshot_paper['paper']
    path = write_snapshot(paper.id, db_session)
    assert path is not None
    data = json.loads(path.read_text())

    # An extra key from a dropped column is tolerated.
    data['tables']['patients'][0]['bogus_removed_column'] = 'x'
    path.write_text(json.dumps(data))
    restore_snapshot(paper.id, path.name, db_session, test_user)

    # A missing NOT-NULL-without-default column is rejected.
    for row in data['tables']['patients']:
        del row['identifier']
    path.write_text(json.dumps(data))
    with pytest.raises(SnapshotIncompatibleError):
        restore_snapshot(paper.id, path.name, db_session, test_user)


def test_worker_hook_writes_snapshot_when_pipeline_done(db_session, snapshot_paper):
    paper = snapshot_paper['paper']
    _maybe_write_snapshot(db_session, paper.id)
    assert len(list_snapshots(paper.id)) == 1


def test_worker_hook_skips_incomplete_pipeline(db_session, snapshot_paper):
    paper = snapshot_paper['paper']
    snapshot_paper['scoped_task'].status = TaskStatus.PENDING
    db_session.flush()
    _maybe_write_snapshot(db_session, paper.id)
    assert list_snapshots(paper.id) == []


def test_worker_hook_ignores_chat_tasks(db_session, snapshot_paper):
    paper = snapshot_paper['paper']
    db_session.add(
        TaskDB(
            paper_id=paper.id,
            agent_run_id=snapshot_paper['agent_run'].id,
            type=TaskType.GENERAL_PAPER_QUESTION,
            status=TaskStatus.PENDING,
        )
    )
    db_session.flush()
    _maybe_write_snapshot(db_session, paper.id)
    assert len(list_snapshots(paper.id)) == 1


def test_snapshots_dir_removed_with_paper(client, db_session, snapshot_paper):
    paper = snapshot_paper['paper']
    write_snapshot(paper.id, db_session)
    # Pre-existing, unrelated to snapshots: the ORM cascade on paper delete
    # cannot topologically sort mutually pair-linked occurrences. Break one
    # direction so this test exercises snapshot-directory cleanup, not that bug.
    snapshot_paper['pvo2'].paired_variant_link_id = None
    db_session.flush()
    directory = snapshots_dir(paper.id)
    assert directory.exists()
    assert client.delete(f'/papers/{paper.id}').status_code == 204
    assert not directory.exists()
