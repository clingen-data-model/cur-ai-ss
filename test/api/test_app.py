import io
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from lib.api.app import app
from lib.api.db import get_session, session_scope
from lib.models import (
    EnrichedVariantDB,
    GeneDB,
    HarmonizedVariantDB,
    PaperDB,
    PatientDB,
    PipelineStatus,
    VariantDB,
)


@pytest.fixture
def client(db_session):
    def override_get_session():
        yield db_session

    @asynccontextmanager
    async def _noop_lifespan(app):
        yield

    # This overrides the app lifespan so it doesn't try to run migrations.
    # DB initialization for tests should be handled by the `db_session` fixture.
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    app.router.lifespan_context = original_lifespan


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


def test_queue_new_paper(client, test_pdf, db_session, seeded_genes):
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
    assert data['pipeline_status'] == PipelineStatus.QUEUED.value
    assert data['filename'] == 'job-1.pdf'
    _assert_updated_at_recent(data['updated_at'])
    count = db_session.scalar(select(func.count(PaperDB.id)))
    assert count == 1


def test_queue_existing_paper_fails(client, db_session, test_pdf, seeded_genes):
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
    assert response2.json()['detail'] == 'Paper extraction already queued'


def test_get_paper_success(client, test_pdf, seeded_genes):
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
    assert data_get['pipeline_status'] == PipelineStatus.QUEUED.value
    assert data_get['filename'] == 'job-1.pdf'
    assert data_get['gene_symbol'] == 'BRCA1'
    _assert_updated_at_recent(data_get['updated_at'])


def test_get_paper_not_found(client):
    response = client.get('/papers/999')
    assert response.status_code == 404
    assert response.json()['detail'] == 'Paper not found'


def test_update_paper_pipeline_status(client, test_pdf, db_session, seeded_genes):
    response = client.put(
        '/papers',
        files={'uploaded_file': ('job-1.pdf', test_pdf, 'application/pdf')},
        data={'gene_symbol': 'BRCA1'},
    )
    data = response.json()
    _assert_updated_at_recent(data['updated_at'])
    db_session.execute(
        update(PaperDB)
        .where(PaperDB.id == data['id'])
        .values(pipeline_status=PipelineStatus.EXTRACTION_FAILED)
    )
    response2 = client.patch(
        f'/papers/{data["id"]}',
        json={'pipeline_status': PipelineStatus.QUEUED.value},
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2['pipeline_status'] == PipelineStatus.QUEUED.value
    _assert_updated_at_recent(data2['updated_at'])
    response3 = client.patch(
        f'/papers/{response2.json()["id"]}',
        json={'pipeline_status': PipelineStatus.QUEUED.value},
    )
    assert response3.status_code == 409
    response4 = client.patch(
        f'/papers/999',
        json={
            'pipeline_status': PipelineStatus.QUEUED.value,
        },
    )
    assert response4.status_code == 404


def test_list_paper(client, test_pdf, seeded_genes):
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


def test_list_papers_filtered_by_status(client, test_pdf, db_session, seeded_genes):
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
    response = client.get(
        '/papers', params={'pipeline_status': PipelineStatus.QUEUED.value}
    )
    assert response.status_code == 200
    jobs = response.json()
    assert all(job['pipeline_status'] == PipelineStatus.QUEUED for job in jobs)
    assert all(job['gene_symbol'] == 'BRCA1' for job in jobs)
    for job in jobs:
        _assert_updated_at_recent(job['updated_at'])


def test_delete_paper(client, test_pdf, db_session, seeded_genes):
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
    gene = GeneDB(symbol='BRCA1')
    db_session.add(gene)
    db_session.flush()
    paper = PaperDB(
        content_hash='abc123',
        gene_id=gene.id,
        filename='test.pdf',
        pipeline_status=PipelineStatus.QUEUED,
    )
    db_session.add(paper)
    db_session.flush()
    return paper


def test_get_patients_empty(client, seeded_paper):
    response = client.get(f'/papers/{seeded_paper.id}/patients')
    assert response.status_code == 200
    assert response.json() == []


def test_get_patients_returns_ordered_by_position(client, db_session, seeded_paper):
    required = dict(
        proband_status='Unknown',
        sex='Unknown',
        country_of_origin='Unknown',
        race_ethnicity='Unknown',
        affected_status='Unknown',
        identifier_evidence=dict(
            value='P', reasoning='test evidence', quote='test context'
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
    )
    # Insert patients in order (they'll get auto-incrementing IDs)
    db_session.add(
        PatientDB(
            paper_id=seeded_paper.id,
            identifier='P3',
            **required,
        )
    )
    db_session.add(
        PatientDB(
            paper_id=seeded_paper.id,
            identifier='P1',
            **required,
        )
    )
    db_session.add(
        PatientDB(
            paper_id=seeded_paper.id,
            identifier='P2',
            **required,
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


def test_update_patient_with_human_edit_note(client, db_session, seeded_paper):
    """Test updating a patient with human_edit_note on evidence."""
    required = dict(
        proband_status='Unknown',
        sex='Unknown',
        country_of_origin='Unknown',
        race_ethnicity='Unknown',
        affected_status='Unknown',
        identifier_evidence=dict(
            value='P1', reasoning='test evidence', quote='test context'
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
    )
    # Create a patient
    patient = PatientDB(
        paper_id=seeded_paper.id,
        identifier='P1',
        **required,
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


def test_get_variants_harmonized_and_enriched(client, db_session, seeded_paper):
    # Create a variant with evidence blocks
    variant = VariantDB(
        paper_id=seeded_paper.id,
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
    enriched = EnrichedVariantDB(
        harmonized_variant_id=harmonized.id,
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
    assert v['enriched_variant'] is not None
    assert v['enriched_variant']['pathogenicity'] == 'Pathogenic'
    assert v['enriched_variant']['submissions'] == 15
    assert v['enriched_variant']['stars'] == 3
    assert v['enriched_variant']['exon'] == '1/24'
    assert v['enriched_variant']['revel'] == 0.89
    assert v['enriched_variant']['alphamissense_class'] == 'likely_pathogenic'
    assert v['enriched_variant']['alphamissense_score'] == 0.75
    assert v['enriched_variant']['spliceai'] == {
        'DS_AG': 0.1,
        'DS_AL': 0.05,
        'DS_DG': 0.2,
        'DS_DL': 0.15,
    }
    assert v['enriched_variant']['gnomad_top_level_af'] == 0.0001
    assert v['enriched_variant']['gnomad_popmax_af'] == 0.0003
    assert v['enriched_variant']['gnomad_popmax_population'] == 'eas'
