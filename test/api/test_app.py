import io
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from lib.api.app import app
from lib.api.auth import get_current_user
from lib.api.db import get_session, session_scope
from lib.core.environment import env
from lib.models import (
    AgentRunDB,
    AnnotatedVariantDB,
    FamilyDB,
    GeneDB,
    HarmonizedVariantDB,
    PaperDB,
    PatientDB,
    PhenotypeDB,
    TaskDB,
    UserDB,
    VariantDB,
)
from lib.tasks import TaskCreateRequest
from lib.tasks.models import TaskStatus, TaskType


@pytest.fixture
def test_pdf():
    # The smallest valid pdf https://pdfa.org/the-smallest-possible-valid-pdf/
    yield io.BytesIO(b"""
%PDF-1.0
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/Resources<<>>/MediaBox[0 0 9 9]>>endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000052 00000 n
0000000101 00000 n
trailer<</Root 1 0 R/Size 4>>
startxref
174
%%EOF""")


def _assert_updated_at_recent(updated_at_str: str, max_age_seconds: int = 60) -> None:
    """Assert that updated_at timestamp is within the last minute."""
    updated_at = datetime.fromisoformat(updated_at_str)
    # Handle naive datetimes by assuming UTC
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    age = (now - updated_at).total_seconds()
    assert 0 <= age <= max_age_seconds, (
        f'updated_at is {age}s old, expected within {max_age_seconds}s'
    )


@pytest.fixture
def seeded_genes(db_session):
    db_session.add_all(
        [
            GeneDB(symbol='BRCA1'),
            GeneDB(symbol='BRCA2'),
            GeneDB(symbol='TP53'),
        ]
    )
    db_session.flush()


def test_queue_new_paper(client, test_pdf, db_session, seeded_genes, agent_run):
    count = db_session.scalar(select(func.count(GeneDB.id)))
    assert count == 3
    response = client.put(
        '/papers',
        files={'uploaded_file': ('job-1.pdf', test_pdf, 'application/pdf')},
        data={'gene_symbol': 'BRCA1'},  # <- add this
    )
    assert response.status_code == 201
    data = response.json()
    assert data['id']  # Paper ID will be generated from content
    assert data['filename'] == 'job-1.pdf'
    assert 'tasks' in data
    assert len(data['tasks']) > 0
    assert all(task['status'] == TaskStatus.PENDING.value for task in data['tasks'])
    _assert_updated_at_recent(data['updated_at'])
    count = db_session.scalar(select(func.count(PaperDB.id)))
    assert count == 1


def test_queue_existing_paper_fails(
    client, db_session, test_pdf, seeded_genes, agent_run
):
    # Second upload: same content/name triggers conflict
    response = client.put(
        '/papers',
        files={'uploaded_file': ('job-1.pdf', test_pdf, 'application/pdf')},
        data={'gene_symbol': 'BRCA1'},
    )
    db_session.commit()  # 👈 make first request durable
    response2 = client.put(
        '/papers',
        files={'uploaded_file': ('job-1.pdf', test_pdf, 'application/pdf')},
        data={'gene_symbol': 'BRCA1'},
    )
    assert response2.status_code == 409
    assert response2.json()['detail'] == 'Paper with this content already exists'


def test_get_paper_success(client, test_pdf, seeded_genes, agent_run):
    upload_response = client.put(
        '/papers',
        files={'uploaded_file': ('job-1.pdf', test_pdf, 'application/pdf')},
        data={'gene_symbol': 'BRCA1'},
    )
    assert upload_response.status_code == 201
    data_upload = upload_response.json()
    paper_id = data_upload['id']
    _assert_updated_at_recent(data_upload['updated_at'])
    get_response = client.get(f'/papers/{paper_id}')
    assert get_response.status_code == 200
    data_get = get_response.json()
    assert data_get['id'] == paper_id
    assert data_get['filename'] == 'job-1.pdf'
    assert data_get['gene_symbol'] == 'BRCA1'
    assert 'tasks' in data_get
    assert len(data_get['tasks']) > 0
    _assert_updated_at_recent(data_get['updated_at'])


def test_get_paper_not_found(client):
    response = client.get('/papers/999')
    assert response.status_code == 404
    assert response.json()['detail'] == 'Paper not found'


def test_update_paper_metadata(client, test_pdf, db_session, seeded_genes, agent_run):
    response = client.put(
        '/papers',
        files={'uploaded_file': ('job-1.pdf', test_pdf, 'application/pdf')},
        data={'gene_symbol': 'BRCA1'},
    )
    data = response.json()
    paper_id = data['id']
    _assert_updated_at_recent(data['updated_at'])
    response2 = client.patch(
        f'/papers/{paper_id}',
        json={'title': 'Updated Title', 'first_author': 'John Doe'},
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2['title'] == 'Updated Title'
    assert data2['first_author'] == 'John Doe'
    _assert_updated_at_recent(data2['updated_at'])
    response3 = client.patch(
        f'/papers/999',
        json={'title': 'Another Title'},
    )
    assert response3.status_code == 404


def test_list_paper(client, test_pdf, seeded_genes, agent_run):
    response = client.put(
        '/papers',
        files={'uploaded_file': ('job-1.pdf', test_pdf, 'application/pdf')},
        data={'gene_symbol': 'BRCA1'},
    )
    response2 = client.put(
        '/papers',
        files={
            'uploaded_file': (
                'job-2.pdf',
                io.BytesIO(test_pdf.getvalue().replace(b'9 9', b'10 9')),
                'application/pdf',
            )
        },
        data={'gene_symbol': 'BRCA1'},
    )
    response = client.get('/papers')
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 2
    for job in jobs:
        _assert_updated_at_recent(job['updated_at'])


def test_list_papers_with_tasks(client, test_pdf, db_session, seeded_genes, agent_run):
    response = client.put(
        '/papers',
        files={'uploaded_file': ('job-1.pdf', test_pdf, 'application/pdf')},
        data={'gene_symbol': 'BRCA1'},
    )
    response2 = client.put(
        '/papers',
        files={
            'uploaded_file': (
                'job-2.pdf',
                io.BytesIO(test_pdf.getvalue().replace(b'9 9', b'10 9')),
                'application/pdf',
            )
        },
        data={'gene_symbol': 'BRCA1'},
    )
    response = client.get('/papers')
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 2
    assert all(job['gene_symbol'] == 'BRCA1' for job in jobs)
    assert all('tasks' in job and len(job['tasks']) > 0 for job in jobs)
    for job in jobs:
        _assert_updated_at_recent(job['updated_at'])


def test_delete_paper(client, test_pdf, db_session, seeded_genes, agent_run):
    response = client.delete(
        f'/papers/999',
    )
    assert response.status_code == 204

    response2 = client.put(
        '/papers',
        files={'uploaded_file': ('job-1.pdf', test_pdf, 'application/pdf')},
        data={'gene_symbol': 'BRCA1'},
    )
    response3 = client.delete(
        f'/papers/{response2.json()["id"]}',
    )
    assert response3.status_code == 204
    result = db_session.execute(select(func.count(PaperDB.id)))
    assert result.scalar_one() == 0


def test_search_genes_by_prefix(client, seeded_genes):
    # Test searching for genes starting with 'BR'
    response = client.get('/genes/search?prefix=BR')
    assert response.status_code == 200
    genes = response.json()
    assert len(genes) == 2
    assert all(gene['symbol'].startswith('BR') for gene in genes)
    symbols = {gene['symbol'] for gene in genes}
    assert symbols == {'BRCA1', 'BRCA2'}


def test_search_genes_by_prefix_single_result(client, seeded_genes):
    # Test searching for genes starting with 'TP'
    response = client.get('/genes/search?prefix=TP')
    assert response.status_code == 200
    genes = response.json()
    assert len(genes) == 1
    assert genes[0]['symbol'] == 'TP53'


def test_search_genes_by_prefix_no_match(client, seeded_genes):
    # Test searching for genes with no matches
    response = client.get('/genes/search?prefix=XYZ')
    assert response.status_code == 200
    genes = response.json()
    assert len(genes) == 0


@pytest.fixture
def seeded_paper(db_session):
    agent_run = AgentRunDB(
        git_hash='abc123def456',
        description='test run',
        model=env.OPENAI_API_DEPLOYMENT,
    )
    db_session.add(agent_run)
    db_session.flush()
    gene = GeneDB(symbol='BRCA1')
    db_session.add(gene)
    db_session.flush()
    paper = PaperDB(
        content_hash='abc123',
        gene_id=gene.id,
        filename='test.pdf',
    )
    db_session.add(paper)
    db_session.flush()
    # Create default family for tests
    family = FamilyDB(
        paper_id=paper.id,
        agent_run_id=agent_run.id,
        identifier='Family 1',
        identifier_evidence=dict(
            value='Family 1', reasoning='test family', quote='Family 1'
        ),
        consanguinity=False,
        consanguinity_evidence=dict(value=False, reasoning='test family', quote='test'),
    )
    db_session.add(family)
    db_session.flush()
    paper.default_family_id = family.id
    return paper


def test_get_patients_empty(client, seeded_paper):
    response = client.get(f'/papers/{seeded_paper.id}/patients')
    assert response.status_code == 200
    assert response.json() == []


def _patient_required_fields(identifier: str = 'P1') -> dict:
    return dict(
        proband_status='Unknown',
        sex='Unknown',
        country_of_origin='Unknown',
        race_ethnicity='Unknown',
        affected_status='Unknown',
        identifier_evidence=dict(
            value=identifier, reasoning='test evidence', quote='test context'
        ),
        proband_status_evidence=dict(
            value='Unknown', reasoning='test evidence', quote='test context'
        ),
        sex_evidence=dict(
            value='Unknown', reasoning='test evidence', quote='test context'
        ),
        age_diagnosis_evidence=dict(
            value=None, reasoning='test evidence', quote='test context'
        ),
        age_report_evidence=dict(
            value=None, reasoning='test evidence', quote='test context'
        ),
        age_death_evidence=dict(
            value=None, reasoning='test evidence', quote='test context'
        ),
        country_of_origin_evidence=dict(
            value='Unknown', reasoning='test evidence', quote='test context'
        ),
        race_ethnicity_evidence=dict(
            value='Unknown', reasoning='test evidence', quote='test context'
        ),
        affected_status_evidence=dict(
            value='Unknown', reasoning='test evidence', quote='test context'
        ),
        family_assignment_evidence=dict(
            value='Family 1', reasoning='test evidence', quote='test context'
        ),
    )


def test_get_patients_returns_ordered_by_position(
    client, db_session, seeded_paper, seeded_agent_run
):
    # Get the default family created in seeded_paper fixture
    family = db_session.query(FamilyDB).filter_by(paper_id=seeded_paper.id).first()
    # Insert patients in order (they'll get auto-incrementing IDs)
    db_session.add(
        PatientDB(
            paper_id=seeded_paper.id,
            family_id=family.id,
            agent_run_id=seeded_agent_run.id,
            identifier='P3',
            **_patient_required_fields('P3'),
        )
    )
    db_session.add(
        PatientDB(
            paper_id=seeded_paper.id,
            family_id=family.id,
            agent_run_id=seeded_agent_run.id,
            identifier='P1',
            **_patient_required_fields('P1'),
        )
    )
    db_session.add(
        PatientDB(
            paper_id=seeded_paper.id,
            family_id=family.id,
            agent_run_id=seeded_agent_run.id,
            identifier='P2',
            **_patient_required_fields('P2'),
        )
    )
    db_session.flush()

    response = client.get(f'/papers/{seeded_paper.id}/patients')
    assert response.status_code == 200
    patients = response.json()
    assert len(patients) == 3
    # Verify ordering by ID (insertion order) - patients get auto-incrementing IDs
    patient_ids = [p['id'] for p in patients]
    assert patient_ids == sorted(patient_ids)  # IDs should be in ascending order
    assert [p['identifier'] for p in patients] == ['P3', 'P1', 'P2']


def test_get_patients_paper_not_found(client):
    response = client.get('/papers/999/patients')
    assert response.status_code == 404
    assert response.json()['detail'] == 'Paper not found'


def test_update_patient_with_human_edit_note(
    client, db_session, seeded_paper, seeded_agent_run
):
    """Test updating a patient with human_edit_note on evidence."""
    # Get the default family created in seeded_paper fixture
    family = db_session.query(FamilyDB).filter_by(paper_id=seeded_paper.id).first()
    # Create a patient
    patient = PatientDB(
        paper_id=seeded_paper.id,
        family_id=family.id,
        agent_run_id=seeded_agent_run.id,
        identifier='P1',
        **_patient_required_fields('P1'),
    )
    db_session.add(patient)
    db_session.flush()
    patient_id = patient.id

    # Update patient with evidence notes
    response = client.patch(
        f'/papers/{seeded_paper.id}/patients/{patient_id}',
        json={
            'identifier_human_edit_note': 'This is a human note about identifier',
            'proband_status_human_edit_note': 'Proband confirmed by clinician',
        },
    )
    assert response.status_code == 200
    resp_json = response.json()

    # Verify the evidence notes were set in the response
    assert (
        resp_json['identifier_evidence']['human_edit_note']
        == 'This is a human note about identifier'
    )
    assert (
        resp_json['proband_status_evidence']['human_edit_note']
        == 'Proband confirmed by clinician'
    )
    # Other evidence should have null notes (only the specified ones were updated)
    assert resp_json['sex_evidence']['human_edit_note'] is None


def test_update_patient_rejects_wrong_paper_scope(
    client, db_session, seeded_paper, seeded_agent_run
):
    other_paper = PaperDB(
        content_hash='other-paper',
        gene_id=seeded_paper.gene_id,
        filename='other.pdf',
    )
    db_session.add(other_paper)
    db_session.flush()

    other_family = FamilyDB(
        paper_id=other_paper.id,
        agent_run_id=seeded_agent_run.id,
        identifier='Other Family',
        identifier_evidence=dict(
            value='Other Family', reasoning='test family', quote='Other Family'
        ),
        consanguinity=False,
        consanguinity_evidence=dict(value=False, reasoning='test family', quote='test'),
    )
    db_session.add(other_family)
    db_session.flush()

    patient = PatientDB(
        paper_id=other_paper.id,
        family_id=other_family.id,
        agent_run_id=seeded_agent_run.id,
        identifier='P-other',
        **_patient_required_fields('P-other'),
    )
    db_session.add(patient)
    db_session.flush()

    response = client.patch(
        f'/papers/{seeded_paper.id}/patients/{patient.id}',
        json={'identifier': 'Wrongly scoped edit'},
    )

    assert response.status_code == 404
    assert response.json()['detail'] == 'Patient not found'
    db_session.refresh(patient)
    assert patient.identifier == 'P-other'


def test_update_phenotype_rejects_wrong_patient_scope(
    client, db_session, seeded_paper, seeded_agent_run
):
    family = db_session.query(FamilyDB).filter_by(paper_id=seeded_paper.id).first()
    patient_1 = PatientDB(
        paper_id=seeded_paper.id,
        family_id=family.id,
        agent_run_id=seeded_agent_run.id,
        identifier='P1',
        **_patient_required_fields('P1'),
    )
    patient_2 = PatientDB(
        paper_id=seeded_paper.id,
        family_id=family.id,
        agent_run_id=seeded_agent_run.id,
        identifier='P2',
        **_patient_required_fields('P2'),
    )
    db_session.add_all([patient_1, patient_2])
    db_session.flush()

    phenotype = PhenotypeDB(
        paper_id=seeded_paper.id,
        patient_id=patient_2.id,
        concept='Seizures',
        concept_evidence=dict(
            value='Seizures', reasoning='test evidence', quote='test context'
        ),
        negated=False,
        uncertain=False,
        family_history=False,
        onset=None,
        location=None,
        severity=None,
        modifier=None,
    )
    db_session.add(phenotype)
    db_session.flush()

    response = client.patch(
        f'/papers/{seeded_paper.id}/patients/{patient_1.id}/phenotypes/{phenotype.id}',
        json={'uncertain': True},
    )

    assert response.status_code == 404
    assert response.json()['detail'] == 'Phenotype not found'
    db_session.refresh(phenotype)
    assert phenotype.uncertain is False


def test_get_variants_harmonized_and_enriched(
    client, db_session, seeded_paper, seeded_agent_run
):
    # Create a variant with evidence blocks
    variant = VariantDB(
        paper_id=seeded_paper.id,
        agent_run_id=seeded_agent_run.id,
        transcript='NM_007294.3',
        protein_accession='NP_009225.1',
        genomic_accession='NC_000017.11',
        lrg_accession=None,
        gene_accession='NG_005905.2',
        genomic_coordinates='17:41196312',
        genome_build='GRCh38',
        rsid='rs80357906',
        caid='CA123456',
        hgvs_c='c.68_69delAG',
        hgvs_p='p.Glu23ValfsTer17',
        hgvs_g='g.41196312_41196313delAG',
        variant_type='Frameshift Deletion',
        functional_evidence=True,
        main_focus=True,
        transcript_evidence={
            'value': 'NM_007294.3',
            'reasoning': 'test',
            'quote': 'test',
        },
        protein_accession_evidence={
            'value': 'NP_009225.1',
            'reasoning': 'test',
            'quote': 'test',
        },
        genomic_accession_evidence={
            'value': 'NC_000017.11',
            'reasoning': 'test',
            'quote': 'test',
        },
        lrg_accession_evidence={'value': None, 'reasoning': 'test'},
        gene_accession_evidence={
            'value': 'NG_005905.2',
            'reasoning': 'test',
            'quote': 'test',
        },
        genomic_coordinates_evidence={
            'value': '17:41196312',
            'reasoning': 'test',
            'quote': 'test',
        },
        genome_build_evidence={'value': 'GRCh38', 'reasoning': 'test', 'quote': 'test'},
        rsid_evidence={'value': 'rs80357906', 'reasoning': 'test', 'quote': 'test'},
        caid_evidence={'value': 'CA123456', 'reasoning': 'test', 'quote': 'test'},
        variant_evidence={
            'value': 'c.68_69delAG',
            'reasoning': 'test',
            'quote': 'test',
        },
        hgvs_c_evidence={'value': 'c.68_69delAG', 'reasoning': 'test', 'quote': 'test'},
        hgvs_p_evidence={
            'value': 'p.Glu23ValfsTer17',
            'reasoning': 'test',
            'quote': 'test',
        },
        hgvs_g_evidence={
            'value': 'g.41196312_41196313delAG',
            'reasoning': 'test',
            'quote': 'test',
        },
        variant_type_evidence={
            'value': 'Frameshift Deletion',
            'reasoning': 'test',
            'quote': 'test',
        },
        functional_evidence_evidence={
            'value': True,
            'reasoning': 'test',
            'quote': 'test',
        },
        main_focus_evidence={
            'value': True,
            'reasoning': 'test',
            'quote': 'test',
        },
    )
    db_session.add(variant)
    db_session.flush()

    # Create harmonized variant
    harmonized = HarmonizedVariantDB(
        variant_id=variant.id,
        gnomad_style_coordinates='17:41196312:AG:A',
        rsid='rs80357906',
        caid='CA123456',
        hgvs_c='c.68_69delAG',
        hgvs_p='p.Glu23ValfsTer17',
        hgvs_g='g.41196312_41196313delAG',
        reasoning='Successfully harmonized to gnomAD coordinates',
    )
    db_session.add(harmonized)
    db_session.flush()

    # Create enriched variant
    enriched = AnnotatedVariantDB(
        variant_id=variant.id,
        pathogenicity='Pathogenic',
        submissions=15,
        stars=3,
        exon='1/24',
        revel=0.89,
        alphamissense_class='likely_pathogenic',
        alphamissense_score=0.75,
        spliceai={'DS_AG': 0.1, 'DS_AL': 0.05, 'DS_DG': 0.2, 'DS_DL': 0.15},
        gnomad_style_coordinates='17:41196312:AG:A',
        rsid='rs80357906',
        caid='CA123456',
        gnomad_top_level_af=0.0001,
        gnomad_popmax_af=0.0003,
        gnomad_popmax_population='eas',
    )
    db_session.add(enriched)
    db_session.commit()

    # Get variants for the paper
    response = client.get(f'/papers/{seeded_paper.id}/variants')
    assert response.status_code == 200
    variants = response.json()
    assert len(variants) == 1

    v = variants[0]
    # Check basic variant data
    assert v['transcript'] == 'NM_007294.3'
    assert v['variant_type'] == 'Frameshift Deletion'
    assert v['main_focus'] is True

    # Check evidence block structure
    assert v['transcript_evidence']['value'] == 'NM_007294.3'
    assert v['transcript_evidence']['reasoning'] == 'test'
    assert v['transcript_evidence']['quote'] == 'test'

    # Check main_focus evidence
    assert v['main_focus_evidence']['value'] is True
    assert v['main_focus_evidence']['reasoning'] == 'test'
    assert v['main_focus_evidence']['quote'] == 'test'

    # Check harmonized data (wrapped in ReasoningBlock)
    assert v['harmonized_variant'] is not None
    assert v['harmonized_variant']['value'] is not None
    assert (
        v['harmonized_variant']['value']['gnomad_style_coordinates']
        == '17:41196312:AG:A'
    )
    assert v['harmonized_variant']['value']['rsid'] == 'rs80357906'
    assert v['harmonized_variant']['value']['caid'] == 'CA123456'
    assert (
        v['harmonized_variant']['reasoning']
        == 'Successfully harmonized to gnomAD coordinates'
    )

    # Check enriched data
    assert v['annotated_variant'] is not None
    assert v['annotated_variant']['pathogenicity'] == 'Pathogenic'
    assert v['annotated_variant']['submissions'] == 15
    assert v['annotated_variant']['stars'] == 3
    assert v['annotated_variant']['exon'] == '1/24'
    assert v['annotated_variant']['revel'] == 0.89
    assert v['annotated_variant']['alphamissense_class'] == 'likely_pathogenic'
    assert v['annotated_variant']['alphamissense_score'] == 0.75
    assert v['annotated_variant']['spliceai'] == {
        'DS_AG': 0.1,
        'DS_AL': 0.05,
        'DS_DG': 0.2,
        'DS_DL': 0.15,
    }
    assert v['annotated_variant']['gnomad_top_level_af'] == 0.0001
    assert v['annotated_variant']['gnomad_popmax_af'] == 0.0003
    assert v['annotated_variant']['gnomad_popmax_population'] == 'eas'


def _ev(value: object = None, quote: str | None = 'test') -> dict:
    """Minimal evidence_block JSON stub for the variant fixture."""
    d: dict = {'value': value, 'reasoning': 'test'}
    if quote is not None and value is not None:
        d['quote'] = quote
    return d


@pytest.fixture
def seeded_agent_run(db_session):
    """Create a test agent run."""
    agent_run = AgentRunDB(
        git_hash='abc123def456',
        description='test run',
        model=env.OPENAI_API_DEPLOYMENT,
    )
    db_session.add(agent_run)
    db_session.flush()
    return agent_run


@pytest.fixture
def seeded_variant(db_session, seeded_paper, seeded_agent_run):
    """Create a variant with a harmonized variant for PATCH tests."""
    variant = VariantDB(
        paper_id=seeded_paper.id,
        agent_run_id=seeded_agent_run.id,
        variant='c.68_69delAG',
        transcript='NM_007294.3',
        genome_build='GRCh38',
        rsid='rs80357906',
        hgvs_c='c.68_69delAG',
        hgvs_p='p.Glu23ValfsTer17',
        variant_type='Frameshift Deletion',
        functional_evidence=True,
        main_focus=False,
        transcript_evidence=_ev('NM_007294.3'),
        protein_accession_evidence=_ev(),
        genomic_accession_evidence=_ev(),
        lrg_accession_evidence=_ev(),
        gene_accession_evidence=_ev(),
        genomic_coordinates_evidence=_ev(),
        genome_build_evidence=_ev('GRCh38'),
        rsid_evidence=_ev('rs80357906'),
        caid_evidence=_ev(),
        variant_evidence=_ev('c.68_69delAG'),
        hgvs_c_evidence=_ev('c.68_69delAG'),
        hgvs_p_evidence=_ev('p.Glu23ValfsTer17'),
        hgvs_g_evidence=_ev(),
        variant_type_evidence=_ev('Frameshift Deletion'),
        functional_evidence_evidence=_ev(True),
        main_focus_evidence=_ev(False),
    )
    db_session.add(variant)
    db_session.flush()
    harmonized = HarmonizedVariantDB(
        variant_id=variant.id,
        gnomad_style_coordinates='17:41196312:AG:A',
        rsid='rs80357906',
        hgvs_c='c.68_69delAG',
        hgvs_p='p.Glu23ValfsTer17',
        reasoning='Harmonized via VariantValidator',
    )
    db_session.add(harmonized)
    db_session.flush()
    db_session.add(
        AnnotatedVariantDB(
            variant_id=variant.id,
            pathogenicity='Pathogenic',
            submissions=3,
            stars=2,
            gnomad_top_level_af=0.0001,
        )
    )
    db_session.flush()
    return variant


@pytest.fixture
def seeded_unharmonized_variant(db_session, seeded_paper, seeded_agent_run):
    """Create a variant without a harmonized variant row for PATCH tests."""
    variant = VariantDB(
        paper_id=seeded_paper.id,
        agent_run_id=seeded_agent_run.id,
        variant='c.100A>G',
        transcript='NM_000000.1',
        genome_build='GRCh38',
        hgvs_c='c.100A>G',
        hgvs_p='p.Lys34Arg',
        variant_type='Missense',
        functional_evidence=False,
        main_focus=False,
        transcript_evidence=_ev('NM_000000.1'),
        protein_accession_evidence=_ev(),
        genomic_accession_evidence=_ev(),
        lrg_accession_evidence=_ev(),
        gene_accession_evidence=_ev(),
        genomic_coordinates_evidence=_ev(),
        genome_build_evidence=_ev('GRCh38'),
        rsid_evidence=_ev(),
        caid_evidence=_ev(),
        variant_evidence=_ev('c.100A>G'),
        hgvs_c_evidence=_ev('c.100A>G'),
        hgvs_p_evidence=_ev('p.Lys34Arg'),
        hgvs_g_evidence=_ev(),
        variant_type_evidence=_ev('Missense'),
        functional_evidence_evidence=_ev(False),
        main_focus_evidence=_ev(False),
    )
    db_session.add(variant)
    db_session.flush()
    return variant


def test_update_variant_extracted_fields(client, seeded_paper, seeded_variant):
    """PATCH variant_type, functional_evidence, and main_focus."""
    response = client.patch(
        f'/papers/{seeded_paper.id}/variants/{seeded_variant.id}',
        json={
            'variant_type': 'Frameshift',
            'functional_evidence': False,
            'main_focus': True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data['variant_type'] == 'Frameshift'
    assert data['functional_evidence'] is False
    assert data['main_focus'] is True
    # Untouched fields remain
    assert data['transcript'] == 'NM_007294.3'


def test_update_variant_harmonized_fields(client, seeded_paper, seeded_variant):
    """PATCH harmonized variant fields through the variant endpoint."""
    response = client.patch(
        f'/papers/{seeded_paper.id}/variants/{seeded_variant.id}',
        json={
            'harmonized_variant': {
                'hgvs_g': 'g.41196312_41196313del',
                'caid': 'CA999999',
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    hv = data['harmonized_variant']['value']
    assert hv['hgvs_g'] == 'g.41196312_41196313del'
    assert hv['caid'] == 'CA999999'
    # Other harmonized fields preserved
    assert hv['rsid'] == 'rs80357906'
    assert hv['hgvs_c'] == 'c.68_69delAG'


def test_update_variant_human_edit_note(client, seeded_paper, seeded_variant):
    """PATCH with a human edit note on an evidence block."""
    response = client.patch(
        f'/papers/{seeded_paper.id}/variants/{seeded_variant.id}',
        json={
            'variant_type': 'Frameshift',
            'variant_type_human_edit_note': 'Reclassified by curator',
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data['variant_type'] == 'Frameshift'
    assert data['variant_type_evidence']['human_edit_note'] == 'Reclassified by curator'


def test_update_variant_not_found(client, seeded_paper):
    """404 for nonexistent variant id."""
    response = client.patch(
        f'/papers/{seeded_paper.id}/variants/999',
        json={'variant_type': 'Missense'},
    )
    assert response.status_code == 404


def test_update_variant_partial(client, seeded_paper, seeded_variant):
    """Partial PATCH only changes the specified fields."""
    response = client.patch(
        f'/papers/{seeded_paper.id}/variants/{seeded_variant.id}',
        json={'main_focus': True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data['main_focus'] is True
    assert data['variant_type'] == 'Frameshift Deletion'
    assert data['functional_evidence'] is True


@pytest.mark.parametrize(
    'field',
    ['variant_type', 'functional_evidence', 'main_focus'],
)
def test_update_variant_rejects_null_non_nullable_fields(
    client, seeded_paper, seeded_variant, field
):
    """PATCH rejects explicit null for non-nullable VariantDB columns."""
    response = client.patch(
        f'/papers/{seeded_paper.id}/variants/{seeded_variant.id}',
        json={field: None},
    )
    assert response.status_code == 422


def test_update_variant_edit_harmonized_clears_enrichment(
    client, db_session, seeded_paper, seeded_variant
):
    """Editing a harmonized field deletes the downstream enriched row."""
    response = client.patch(
        f'/papers/{seeded_paper.id}/variants/{seeded_variant.id}',
        json={'harmonized_variant': {'hgvs_g': 'g.41196312_41196313del'}},
    )
    assert response.status_code == 200
    assert response.json()['annotated_variant'] is None
    # Row is actually gone, not just hidden from the response.
    remaining = (
        db_session.query(AnnotatedVariantDB)
        .filter(AnnotatedVariantDB.variant_id == seeded_variant.id)
        .count()
    )
    assert remaining == 0


def test_update_variant_edit_harmonized_hgvs_p_also_clears_enrichment(
    client, seeded_paper, seeded_variant
):
    """Uniform sibling treatment: editing hgvs_p (currently not an enrichment
    lookup input) still clears enrichment, so a future lookup that starts
    reading hgvs_p cannot silently produce stale annotations.
    """
    response = client.patch(
        f'/papers/{seeded_paper.id}/variants/{seeded_variant.id}',
        json={'harmonized_variant': {'hgvs_p': 'p.Glu23Ter'}},
    )
    assert response.status_code == 200
    assert response.json()['annotated_variant'] is None


def test_update_variant_edit_harmonized_preserves_reasoning(
    client, seeded_paper, seeded_variant
):
    """A harmonized-field edit leaves the LLM reasoning untouched: it is the
    agent's explanation of its original choices and must remain auditable.
    The curator's rationale goes into human_edit_note fields instead.
    """
    response = client.patch(
        f'/papers/{seeded_paper.id}/variants/{seeded_variant.id}',
        json={'harmonized_variant': {'caid': 'CA999999'}},
    )
    assert response.status_code == 200
    assert (
        response.json()['harmonized_variant']['reasoning']
        == 'Harmonized via VariantValidator'
    )


def test_update_variant_edit_extracted_only_preserves_derived(
    client, seeded_paper, seeded_variant
):
    """Editing variant_type / functional_evidence / main_focus leaves
    harmonized reasoning and enrichment untouched (assumption A1).
    """
    response = client.patch(
        f'/papers/{seeded_paper.id}/variants/{seeded_variant.id}',
        json={'variant_type': 'Frameshift', 'main_focus': True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data['annotated_variant'] is not None
    assert data['annotated_variant']['pathogenicity'] == 'Pathogenic'
    assert data['harmonized_variant']['reasoning'] == 'Harmonized via VariantValidator'


def test_update_variant_edit_only_note_preserves_derived(
    client, seeded_paper, seeded_variant
):
    """PATCHing only a human_edit_note does not invalidate any derived data."""
    response = client.patch(
        f'/papers/{seeded_paper.id}/variants/{seeded_variant.id}',
        json={'variant_type_human_edit_note': 'Reviewed'},
    )
    assert response.status_code == 200
    data = response.json()
    assert data['annotated_variant'] is not None
    assert data['harmonized_variant']['reasoning'] == 'Harmonized via VariantValidator'


def test_update_variant_rejects_old_flat_harmonized_shape(
    client, seeded_paper, seeded_variant
):
    """Old top-level harmonized_* fields are rejected instead of ignored."""
    response = client.patch(
        f'/papers/{seeded_paper.id}/variants/{seeded_variant.id}',
        json={'harmonized_hgvs_g': 'g.41196312_41196313del'},
    )
    assert response.status_code == 422


def test_update_variant_rejects_null_harmonized_variant(
    client, seeded_paper, seeded_variant
):
    """Omitting harmonized_variant is allowed, but explicit null is not."""
    response = client.patch(
        f'/papers/{seeded_paper.id}/variants/{seeded_variant.id}',
        json={'harmonized_variant': None},
    )
    assert response.status_code == 422


def test_update_variant_clears_nested_harmonized_field(
    client, seeded_paper, seeded_variant
):
    """Nested harmonized fields may be explicitly cleared with null."""
    response = client.patch(
        f'/papers/{seeded_paper.id}/variants/{seeded_variant.id}',
        json={'harmonized_variant': {'hgvs_p': None}},
    )
    assert response.status_code == 200
    hv = response.json()['harmonized_variant']['value']
    assert hv['hgvs_p'] is None
    assert hv['rsid'] == 'rs80357906'
    assert hv['hgvs_c'] == 'c.68_69delAG'


def test_enqueue_all_instances_for_splatted_task(
    client, seeded_paper, db_session, agent_run
):
    """Test re-enqueueing a splatted task with no entity IDs re-queues all instances."""
    # Create families and splatted tasks
    family1 = FamilyDB(
        paper_id=seeded_paper.id,
        agent_run_id=agent_run.id,
        identifier='fam1',
        identifier_evidence={},
        consanguinity=False,
        consanguinity_evidence={},
    )
    family2 = FamilyDB(
        paper_id=seeded_paper.id,
        agent_run_id=agent_run.id,
        identifier='fam2',
        identifier_evidence={},
        consanguinity=False,
        consanguinity_evidence={},
    )
    db_session.add_all([family1, family2])
    db_session.flush()

    # Create per-family tasks and mark them as completed
    task1 = TaskDB(
        paper_id=seeded_paper.id,
        agent_run_id=agent_run.id,
        type=TaskType.SEGREGATION_EVIDENCE_EXTRACTION,
        family_id=family1.id,
        status=TaskStatus.COMPLETED,
    )
    task2 = TaskDB(
        paper_id=seeded_paper.id,
        agent_run_id=agent_run.id,
        type=TaskType.SEGREGATION_EVIDENCE_EXTRACTION,
        family_id=family2.id,
        status=TaskStatus.COMPLETED,
    )
    db_session.add_all([task1, task2])
    db_session.commit()

    # Re-enqueue without entity IDs - should reset all instances to PENDING
    response = client.post(
        f'/papers/{seeded_paper.id}/tasks',
        json=TaskCreateRequest(
            type=TaskType.SEGREGATION_EVIDENCE_EXTRACTION,
        ).model_dump(),
    )
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 2
    assert all(t['status'] == 'Pending' for t in tasks)
    assert {t['family_id'] for t in tasks} == {family1.id, family2.id}


def test_enqueue_clears_conversation_id_without_context(
    client, seeded_paper, db_session, agent_run
):
    """Test that re-enqueueing without additional_context clears conversation_id."""
    # Create a task with existing conversation_id and additional_context
    task = TaskDB(
        paper_id=seeded_paper.id,
        agent_run_id=agent_run.id,
        type=TaskType.HPO_LINKING,
        status=TaskStatus.COMPLETED,
        conversation_id='conv-123',
        additional_context='old context',
    )
    db_session.add(task)
    db_session.commit()

    # Re-enqueue without additional_context - should clear conversation_id
    response = client.post(
        f'/papers/{seeded_paper.id}/tasks',
        json=TaskCreateRequest(
            type=TaskType.HPO_LINKING,
        ).model_dump(),
    )
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 1
    assert tasks[0]['conversation_id'] is None
    assert tasks[0]['additional_context'] is None
    assert tasks[0]['status'] == 'Pending'


def test_update_variant_rejects_harmonized_update_before_harmonization(
    client, seeded_paper, seeded_unharmonized_variant
):
    """A valid harmonized update conflicts with a variant lacking a harmonized row."""
    response = client.patch(
        f'/papers/{seeded_paper.id}/variants/{seeded_unharmonized_variant.id}',
        json={'harmonized_variant': {'hgvs_g': 'g.100A>G'}},
    )
    assert response.status_code == 409
    assert (
        response.json()['detail'] == 'Variant has not been harmonized by the server yet'
    )


def test_cache_headers_on_static_files(client):
    """Test that static files get 24-hour cache headers."""
    # Mock a static file request by calling a path under CAA_ROOT
    response = client.get(f'{env.CAA_ROOT}/extracted_pdfs/1/thumbnail.png')
    # Even if 404, the cache header middleware should have run
    assert response.headers.get('Cache-Control') == 'public, max-age=86400'


def test_no_cache_headers_on_api_endpoints(client):
    """Test that API endpoints don't get static file cache headers."""
    response = client.get('/status')
    assert response.status_code == 200
    # Should not have the static file cache header
    cache_control = response.headers.get('Cache-Control')
    assert cache_control != 'public, max-age=86400'


# ---------------------------------------------------------------------------
# Authentication on domain endpoints
#
# Pure auth-flow tests (register/login/me/change-password) live in test_auth.py;
# these cover how the domain (PATCH) endpoints enforce and record the user.
# ---------------------------------------------------------------------------


def test_patch_requires_authentication(unauth_client, seeded_paper):
    # No current-user override here: the PATCH endpoint must reject anonymous edits.
    resp = unauth_client.patch(
        f'/papers/{seeded_paper.id}', json={'title': 'New Title'}
    )
    assert resp.status_code == 401


def test_patch_patient_records_updated_by(
    client, db_session, seeded_paper, seeded_agent_run, test_user
):
    family = db_session.query(FamilyDB).filter_by(paper_id=seeded_paper.id).first()
    patient = PatientDB(
        paper_id=seeded_paper.id,
        family_id=family.id,
        agent_run_id=seeded_agent_run.id,
        identifier='P1',
        **_patient_required_fields('P1'),
    )
    db_session.add(patient)
    db_session.flush()

    resp = client.patch(
        f'/papers/{seeded_paper.id}/patients/{patient.id}',
        json={'identifier': 'P1-edited'},
    )
    assert resp.status_code == 200
    assert resp.json()['updated_by_user_id'] == test_user.id
