import io
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from lib.api.app import app
from lib.api.db import get_session, session_scope
from lib.models import ExtractionStatus, GeneDB, PaperDB, PatientDB, VariantDB


@pytest.fixture
def client(db_session):
    def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    # Replace the lifespan to avoid Alembic running during tests
    # (db_session fixture already creates tables via create_all)
    @asynccontextmanager
    async def _noop_lifespan(app):  # type: ignore
        yield

    original_router_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    with TestClient(app) as client:
        yield client
    app.router.lifespan_context = original_router_lifespan
    app.dependency_overrides.clear()


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
    assert data['extraction_status'] == ExtractionStatus.QUEUED.value
    assert data['filename'] == 'job-1.pdf'
    count = db_session.scalar(select(func.count(PaperDB.id)))
    assert count == 1


def test_queue_existing_paper_fails(client, test_pdf, seeded_genes):
    # Second upload: same content/name triggers conflict
    response = client.put(
        '/papers',
        files={'uploaded_file': ('job-1.pdf', test_pdf, 'application/pdf')},
        data={'gene_symbol': 'BRCA1'},
    )
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
    get_response = client.get(f'/papers/{paper_id}')
    assert get_response.status_code == 200
    data_get = get_response.json()
    assert data_get['id'] == paper_id
    assert data_get['extraction_status'] == ExtractionStatus.QUEUED.value
    assert data_get['filename'] == 'job-1.pdf'


def test_get_paper_not_found(client):
    response = client.get('/papers/missing')
    assert response.status_code == 404
    assert response.json()['detail'] == 'Paper not found'


def test_update_paper_extraction_status(client, test_pdf, db_session, seeded_genes):
    response = client.put(
        '/papers',
        files={'uploaded_file': ('job-1.pdf', test_pdf, 'application/pdf')},
        data={'gene_symbol': 'BRCA1'},
    )
    data = response.json()
    db_session.execute(
        update(PaperDB)
        .where(PaperDB.id == data['id'])
        .values(extraction_status=ExtractionStatus.FAILED)
    )
    response2 = client.patch(
        f'/papers/{data["id"]}',
        json={'extraction_status': ExtractionStatus.QUEUED.value},
    )
    assert response2.status_code == 200
    assert response2.json()['extraction_status'] == ExtractionStatus.QUEUED.value
    response3 = client.patch(
        f'/papers/{response2.json()["id"]}',
        json={'extraction_status': ExtractionStatus.QUEUED.value},
    )
    assert response3.status_code == 409
    response4 = client.patch(
        f'/papers/abcd',
        json={
            'extraction_status': ExtractionStatus.QUEUED.value,
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
        '/papers', params={'extraction_status': ExtractionStatus.QUEUED.value}
    )
    assert response.status_code == 200
    jobs = response.json()
    assert all(job['extraction_status'] == ExtractionStatus.QUEUED for job in jobs)


def test_delete_paper(client, test_pdf, db_session, seeded_genes):
    response = client.delete(
        f'/papers/abcd',
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


def _create_paper_with_extraction_data(db_session, client, test_pdf, seeded_genes):
    """Helper: create a paper and seed patients + variants."""
    response = client.put(
        '/papers',
        files={'uploaded_file': ('job-1.pdf', test_pdf, 'application/pdf')},
        data={'gene_symbol': 'BRCA1'},
    )
    paper_id = response.json()['id']
    # Add patients
    db_session.add_all(
        [
            PatientDB(
                paper_id=paper_id,
                identifier='Patient 1',
                sex='Male',
                country_of_origin='United States',
                race_ethnicity='Non-Finnish European',
            ),
            PatientDB(
                paper_id=paper_id,
                identifier='Patient 2',
                sex='Female',
            ),
        ]
    )
    # Add variants
    db_session.add_all(
        [
            VariantDB(
                paper_id=paper_id,
                gene='BRCA1',
                variant_verbatim='c.1799T>A',
                variant_type='missense',
                zygosity='heterozygous',
                inheritance='dominant',
            ),
        ]
    )
    db_session.flush()
    return paper_id


def test_list_paper_patients(client, test_pdf, db_session, seeded_genes):
    paper_id = _create_paper_with_extraction_data(
        db_session, client, test_pdf, seeded_genes
    )
    response = client.get(f'/papers/{paper_id}/patients')
    assert response.status_code == 200
    patients = response.json()
    assert len(patients) == 2
    assert patients[0]['identifier'] == 'Patient 1'
    assert patients[0]['paper_id'] == paper_id
    assert patients[1]['identifier'] == 'Patient 2'


def test_list_paper_patients_not_found(client):
    response = client.get('/papers/nonexistent/patients')
    assert response.status_code == 404


def test_list_paper_variants(client, test_pdf, db_session, seeded_genes):
    paper_id = _create_paper_with_extraction_data(
        db_session, client, test_pdf, seeded_genes
    )
    response = client.get(f'/papers/{paper_id}/variants')
    assert response.status_code == 200
    variants = response.json()
    assert len(variants) == 1
    assert variants[0]['gene'] == 'BRCA1'
    assert variants[0]['variant_verbatim'] == 'c.1799T>A'
    assert variants[0]['paper_id'] == paper_id


def test_list_paper_variants_not_found(client):
    response = client.get('/papers/nonexistent/variants')
    assert response.status_code == 404


def test_paper_resp_includes_metadata(client, test_pdf, db_session, seeded_genes):
    response = client.put(
        '/papers',
        files={'uploaded_file': ('job-1.pdf', test_pdf, 'application/pdf')},
        data={'gene_symbol': 'BRCA1'},
    )
    paper_id = response.json()['id']
    # Update metadata on the paper
    paper_db = db_session.get(PaperDB, paper_id)
    paper_db.title = 'Test Paper Title'
    paper_db.pmid = '12345'
    paper_db.is_open_access = True
    db_session.flush()

    get_response = client.get(f'/papers/{paper_id}')
    assert get_response.status_code == 200
    data = get_response.json()
    assert data['title'] == 'Test Paper Title'
    assert data['pmid'] == '12345'
    assert data['is_open_access'] is True
    assert data['abstract'] is None


def test_delete_paper_cascades_patients_variants(
    client, test_pdf, db_session, seeded_genes
):
    paper_id = _create_paper_with_extraction_data(
        db_session, client, test_pdf, seeded_genes
    )
    # Verify data exists
    assert db_session.scalar(select(func.count(PatientDB.id))) == 2
    assert db_session.scalar(select(func.count(VariantDB.id))) == 1

    # Delete paper
    response = client.delete(f'/papers/{paper_id}')
    assert response.status_code == 204

    # Verify cascade
    assert db_session.scalar(select(func.count(PatientDB.id))) == 0
    assert db_session.scalar(select(func.count(VariantDB.id))) == 0
