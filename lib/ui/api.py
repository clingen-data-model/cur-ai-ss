import requests
import streamlit as st
import streamlit.runtime.uploaded_file_manager
from pydantic import TypeAdapter

from lib.core.environment import env
from lib.misc.pdf.highlight import GrobidAnnotation
from lib.models import GeneResp, PaperResp, PaperUpdateRequest, PipelineStatus


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
    resp = requests.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/papers')
    resp.raise_for_status()
    return TypeAdapter(list[PaperResp]).validate_python(resp.json())


def search_genes(prefix: str, limit: int = 10) -> list[GeneResp]:
    resp = requests.get(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/genes/search',
        params={'prefix': prefix, 'limit': limit},
    )
    resp.raise_for_status()
    return TypeAdapter(list[GeneResp]).validate_python(resp.json())


def get_paper(paper_id: str) -> PaperResp:
    resp = requests.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}')
    resp.raise_for_status()
    return PaperResp.model_validate(resp.json())


def put_paper(
    uploaded_file: streamlit.runtime.uploaded_file_manager.UploadedFile,
    gene_symbol: str,
) -> PaperResp:
    resp = requests.put(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers',
        data={'gene_symbol': gene_symbol},
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


def update_paper(paper_id: str, update_request: PaperUpdateRequest) -> PaperResp:
    resp = requests.patch(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}',
        json=update_request.model_dump(mode='json'),
    )
    resp.raise_for_status()
    return PaperResp.model_validate(resp.json())


def delete_paper(paper_id: str) -> None:
    resp = requests.delete(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}',
    )
    resp.raise_for_status()


def highlight_pdf(paper_id: str, queries: list[str] | str, color: str) -> None:
    if isinstance(queries, str):
        queries = [queries]
    resp = requests.post(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/highlight',
        json={'queries': queries, 'color': color},
    )
    resp.raise_for_status()


def grobid_annotations(
    paper_id: str, queries: list[str] | str, color: str
) -> list[GrobidAnnotation]:
    if isinstance(queries, str):
        queries = [queries]
    resp = requests.post(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/grobid-annotation',
        json={'queries': queries, 'color': color},
    )
    resp.raise_for_status()
    return TypeAdapter(list[GrobidAnnotation]).validate_python(resp.json())
