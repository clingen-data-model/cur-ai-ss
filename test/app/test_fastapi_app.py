import pytest
from fastapi.testclient import TestClient

from app.db import get_session
from app.fastapi_app import app
from app.models import ExtractionStatus


@pytest.fixture
def client(test_db):
    with TestClient(app) as client:
        yield client


def test_queue_new_job(client):
    response = client.put(
        '/papers',
        json={'id': 'job-1'},
    )
    assert response.status_code == 200
    data = response.json()
    assert data['id'] == 'job-1'
    assert data['status'] == ExtractionStatus.QUEUED


def test_queue_existing_queued_job_fails(client):
    client.put('/papers', json={'id': 'job-1'})
    response = client.put('/papers', json={'id': 'job-1'})
    assert response.status_code == 404
    assert response.json()['detail'] == 'Paper extraction already running'


def test_get_job_success(client):
    client.put('/papers', json={'id': 'job-1'})
    response = client.get('/papers/job-1')
    assert response.status_code == 200
    assert response.json()['id'] == 'job-1'


def test_get_job_not_found(client):
    response = client.get('/papers/missing')
    assert response.status_code == 404
    assert response.json()['detail'] == 'Paper not found'


def test_list_jobs(client):
    client.put('/papers', json={'id': 'job-5'})
    client.put('/papers', json={'id': 'job-6'})
    response = client.get('/papers')
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 2


def test_list_jobs_filtered_by_status(client):
    client.put('/papers', json={'id': 'job-7'})
    client.put('/papers', json={'id': 'job-8'})
    response = client.get('/papers', params={'status': ExtractionStatus.QUEUED.value})
    assert response.status_code == 200
    jobs = response.json()
    assert all(job['status'] == ExtractionStatus.QUEUED for job in jobs)
