import requests

from app.models import ExtractionStatus
from lib.evagg.types.base import Paper
from lib.evagg.utils.environment import env

FASTAPI_HOST = f'http://{env.API_ENDPOINT}:{env.API_PORT}'


def get_http_error_detail(e: requests.HTTPError) -> str:
    """Safely extract the 'detail' from an HTTPError response."""
    if e.response is not None:
        try:
            return e.response.json().get('detail', e.response.text)
        except ValueError:
            # Response is not JSON
            return e.response.text
    return str(e)


def get_papers():
    resp = requests.get(f'{FASTAPI_HOST}/papers')
    resp.raise_for_status()
    return resp.json()


def get_paper(paper_id: str):
    resp = requests.get(f'{FASTAPI_HOST}/papers/{paper_id}')
    resp.raise_for_status()
    return resp.json()


def put_paper(uploaded_file):
    resp = requests.put(
        f'{FASTAPI_HOST}/papers',
        files={
            'uploaded_file': (
                uploaded_file.name,
                uploaded_file.read(),
                'application/pdf',
            )
        },
        # Content type is multipart/form-data
    )
    resp.raise_for_status()
    return resp.json()


def requeue_paper(paper_id: str):
    resp = requests.patch(
        f'{FASTAPI_HOST}/papers/{paper_id}', 
        json={'extraction_status': ExtractionStatus.QUEUED.value}
    )
    resp.raise_for_status()
    return resp.json()
