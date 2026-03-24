import requests
import streamlit as st
import streamlit.runtime.uploaded_file_manager
from pydantic import TypeAdapter

from lib.core.environment import env
from lib.misc.pdf.highlight import GrobidAnnotation
from lib.models import (
    ExtractedVariantResp,
    GeneResp,
    PaperResp,
    PaperUpdateRequest,
    PatientResp,
    PatientUpdateRequest,
    PedigreeResp,
    PipelineStatus,
)


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
        params={'prefix': prefix, 'limit': str(limit)},
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
    supplement_file: streamlit.runtime.uploaded_file_manager.UploadedFile | None = None,
) -> PaperResp:
    files = {
        'uploaded_file': (
            uploaded_file.name,
            uploaded_file.read(),
            'application/pdf',
        )
    }
    if supplement_file:
        files['supplement_file'] = (
            supplement_file.name,
            supplement_file.read(),
            'application/pdf',
        )

    resp = requests.put(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers',
        data={'gene_symbol': gene_symbol},
        files=files,
        # Content type is multipart/form-data
    )
    resp.raise_for_status()
    return PaperResp.model_validate(resp.json())


def update_paper(paper_id: str, update_request: PaperUpdateRequest) -> PaperResp:
    resp = requests.patch(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}',
        json=update_request.model_dump(mode='json', exclude_unset=True),
    )
    resp.raise_for_status()
    return PaperResp.model_validate(resp.json())


def delete_paper(paper_id: str) -> None:
    resp = requests.delete(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}',
    )
    resp.raise_for_status()


def highlight_pdf(
    paper_id: str, queries: list[str], image_ids: list[int], color: str
) -> None:
    if isinstance(queries, str):
        queries = [queries]
    resp = requests.post(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/highlight',
        json={'queries': queries, 'image_ids': image_ids, 'color': color},
    )
    resp.raise_for_status()


def grobid_annotations(
    paper_id: str, queries: list[str], image_ids: list[int], color: str
) -> list[GrobidAnnotation]:
    resp = requests.post(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/grobid-annotation',
        json={'queries': queries, 'image_ids': image_ids, 'color': color},
    )
    resp.raise_for_status()
    return TypeAdapter(list[GrobidAnnotation]).validate_python(resp.json())


def get_patients(paper_id: str) -> list[PatientResp]:
    resp = requests.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/patients')
    resp.raise_for_status()
    return TypeAdapter(list[PatientResp]).validate_python(resp.json())


def get_pedigree(paper_id: str) -> PedigreeResp | None:
    resp = requests.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/pedigree')
    resp.raise_for_status()
    data = resp.json()
    return PedigreeResp.model_validate(data) if data else None


def update_patient(
    paper_id: str, patient_idx: int, update_request: PatientUpdateRequest
) -> PatientResp:
    resp = requests.patch(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/patients/{patient_idx}',
        json=update_request.model_dump(mode='json', exclude_unset=True),
    )
    resp.raise_for_status()
    return PatientResp.model_validate(resp.json())


def get_variants(paper_id: str) -> list[ExtractedVariantResp]:
    resp = requests.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/variants')
    resp.raise_for_status()
    return TypeAdapter(list[ExtractedVariantResp]).validate_python(resp.json())


def clear_highlights(paper_id: str) -> None:
    resp = requests.post(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/clear-highlights',
    )
    resp.raise_for_status()
