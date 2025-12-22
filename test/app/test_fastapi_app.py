import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.db import session_scope
from app.fastapi_app import app
from app.models import ExtractionStatus, PaperDB


@pytest.fixture
def client(test_db):
    with TestClient(app) as client:
        yield client


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


def test_queue_new_paper(client, test_pdf):
    response = client.put(
        '/papers', files={'uploaded_file': ('job-1.pdf', test_pdf, 'application/pdf')}
    )
    assert response.status_code == 201
    data = response.json()
    assert data['id']  # Paper ID will be generated from content
    assert data['extraction_status'] == ExtractionStatus.QUEUED.value
    assert data['filename'] == 'job-1.pdf'
    assert 'thumbnail_path' in data
    assert 'raw_path' in data


def test_queue_existing_paper_fails(client, test_pdf):
    # Second upload: same content/name triggers conflict
    response = client.put(
        '/papers', files={'uploaded_file': ('job-1.pdf', test_pdf, 'application/pdf')}
    )
    response2 = client.put(
        '/papers', files={'uploaded_file': ('job-1.pdf', test_pdf, 'application/pdf')}
    )
    assert response2.status_code == 409
    assert response2.json()['detail'] == 'Paper extraction already queued'


def test_get_paper_success(client, test_pdf):
    upload_response = client.put(
        '/papers', files={'uploaded_file': ('job-1.pdf', test_pdf, 'application/pdf')}
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
    assert 'thumbnail_path' in data_get
    assert 'raw_path' in data_get


def test_get_paper_not_found(client):
    response = client.get('/papers/missing')
    assert response.status_code == 404
    assert response.json()['detail'] == 'Paper not found'


def test_update_paper_extraction_status(client, test_pdf):
    response = client.put(
        '/papers', files={'uploaded_file': ('job-1.pdf', test_pdf, 'application/pdf')}
    )
    data = response.json()
    with session_scope() as sess:
        sess.execute(
            update(PaperDB)
            .where(PaperDB.id == data['id'])
            .values(extraction_status=ExtractionStatus.FAILED)
        )
        sess.commit()

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


def test_list_paper(client, test_pdf):
    response = client.put(
        '/papers', files={'uploaded_file': ('job-1.pdf', test_pdf, 'application/pdf')}
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
    )
    response = client.get('/papers')
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 2


def test_list_papers_filtered_by_status(client, test_pdf):
    response = client.put(
        '/papers', files={'uploaded_file': ('job-1.pdf', test_pdf, 'application/pdf')}
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
    )
    response = client.get(
        '/papers', params={'extraction_status': ExtractionStatus.QUEUED.value}
    )
    assert response.status_code == 200
    jobs = response.json()
    assert all(job['extraction_status'] == ExtractionStatus.QUEUED for job in jobs)
