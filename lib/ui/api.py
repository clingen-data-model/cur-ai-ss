import requests
import streamlit as st
import streamlit.runtime.uploaded_file_manager
from pydantic import TypeAdapter

from lib.evagg.types.base import Paper
from lib.evagg.utils.environment import env
from lib.models import ExtractionStatus, GeneResp, PaperResp, PatientResp, VariantResp


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


@st.cache_data(ttl='1d')
def get_genes() -> list[GeneResp]:
    resp = requests.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/genes')
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


def requeue_paper(paper_id: str) -> PaperResp:
    resp = requests.patch(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}',
        json={'extraction_status': ExtractionStatus.QUEUED.value},
    )
    resp.raise_for_status()
    return PaperResp.model_validate(resp.json())


def delete_paper(paper_id: str) -> None:
    resp = requests.delete(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}',
    )
    resp.raise_for_status()


def get_paper_patients(paper_id: str) -> list[PatientResp]:
    resp = requests.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/patients')
    resp.raise_for_status()
    return TypeAdapter(list[PatientResp]).validate_python(resp.json())


def get_paper_variants(paper_id: str) -> list[VariantResp]:
    resp = requests.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/variants')
    resp.raise_for_status()
    return TypeAdapter(list[VariantResp]).validate_python(resp.json())
