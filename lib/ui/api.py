import requests
from pydantic import TypeAdapter

from lib.evagg.types.base import Paper
from lib.evagg.utils.environment import env
from lib.models import ExtractionStatus, PaperResp


def get_http_error_detail(e: requests.HTTPError) -> str:
    """Safely extract the 'detail' from an HTTPError response."""
    if e.response is not None:
        try:
            return e.response.json().get('detail', e.response.text)
        except ValueError:
            # Response is not JSON
            return e.response.text
    return str(e)


def get_papers() -> list[PaperResp]:
    resp = requests.get(f'http://{env.API_ENDPOINT}:{env.API_PORT}/papers')
    resp.raise_for_status()
    return TypeAdapter(list[PaperResp]).validate_python(resp.json())


def get_paper(paper_id: str) -> PaperResp:
    resp = requests.get(f'http://{env.API_ENDPOINT}:{env.API_PORT}/papers/{paper_id}')
    resp.raise_for_status()
    return PaperResp.model_validate(resp.json())


def put_paper(uploaded_file) -> PaperResp:
    resp = requests.put(
        f'http://{env.API_ENDPOINT}:{env.API_PORT}/papers',
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
    return PaperResp.model_validate(resp.json())


def requeue_paper(paper_id: str) -> PaperResp:
    resp = requests.patch(
        f'http://{env.API_ENDPOINT}:{env.API_PORT}/papers/{paper_id}',
        json={'extraction_status': ExtractionStatus.QUEUED.value},
    )
    resp.raise_for_status()
    return PaperResp.model_validate(resp.json())


def delete_paper(paper_id: str) -> None:
    resp = requests.delete(
        f'{FASTAPI_HOST}/papers/{paper_id}',
    )
    resp.raise_for_status()
