import requests
import streamlit as st
import streamlit.runtime.uploaded_file_manager
from pydantic import TypeAdapter

from lib.core.environment import env
from lib.misc.pdf.highlight import GrobidAnnotation
from lib.models import (
    FamilyResp,
    GeneResp,
    PaperResp,
    PaperUpdateRequest,
    PatientResp,
    PatientUpdateRequest,
    PatientVariantLinkResp,
    PedigreeResp,
    PhenotypeResp,
    TaskResp,
    VariantResp,
    VariantUpdateRequest,
)
from lib.tasks import TaskCreateRequest, TaskType, infer_paper_status


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


def get_paper(paper_id: int) -> PaperResp:
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


def update_paper(paper_id: int, update_request: PaperUpdateRequest) -> PaperResp:
    resp = requests.patch(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}',
        json=update_request.model_dump(mode='json', exclude_unset=True),
    )
    resp.raise_for_status()
    return PaperResp.model_validate(resp.json())


def delete_paper(paper_id: int) -> None:
    resp = requests.delete(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}',
    )
    resp.raise_for_status()


def highlight_pdf(
    paper_id: int,
    queries: list[str],
    image_ids: list[int],
    table_ids: list[int],
    color: str,
) -> None:
    if isinstance(queries, str):
        queries = [queries]
    resp = requests.post(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/highlight',
        json={
            'queries': queries,
            'image_ids': image_ids,
            'table_ids': table_ids,
            'color': color,
        },
    )
    resp.raise_for_status()


def grobid_annotations(
    paper_id: int,
    queries: list[str],
    image_ids: list[int],
    table_ids: list[int],
    color: str,
) -> list[GrobidAnnotation]:
    resp = requests.post(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/grobid-annotation',
        json={
            'queries': queries,
            'image_ids': image_ids,
            'table_ids': table_ids,
            'color': color,
        },
    )
    resp.raise_for_status()
    return TypeAdapter(list[GrobidAnnotation]).validate_python(resp.json())


def get_patients(paper_id: int) -> list[PatientResp]:
    resp = requests.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/patients')
    resp.raise_for_status()
    return TypeAdapter(list[PatientResp]).validate_python(resp.json())


def get_families(paper_id: int) -> list[FamilyResp]:
    resp = requests.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/families')
    resp.raise_for_status()
    return TypeAdapter(list[FamilyResp]).validate_python(resp.json())


def get_pedigree(paper_id: int) -> PedigreeResp | None:
    resp = requests.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/pedigree')
    resp.raise_for_status()
    data = resp.json()
    return PedigreeResp.model_validate(data) if data else None


def update_patient(
    paper_id: int, patient_id: int, update_request: PatientUpdateRequest
) -> PatientResp:
    resp = requests.patch(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/patients/{patient_id}',
        json=update_request.model_dump(mode='json', exclude_unset=True),
    )
    resp.raise_for_status()
    return PatientResp.model_validate(resp.json())


def get_variants(paper_id: int) -> list[VariantResp]:
    resp = requests.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/variants')
    resp.raise_for_status()
    return TypeAdapter(list[VariantResp]).validate_python(resp.json())


def update_variant(
    paper_id: int, variant_id: int, update_request: VariantUpdateRequest
) -> VariantResp:
    resp = requests.patch(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/variants/{variant_id}',
        json=update_request.model_dump(mode='json', exclude_unset=True),
    )
    resp.raise_for_status()
    return VariantResp.model_validate(resp.json())


def clear_highlights(paper_id: int) -> None:
    resp = requests.post(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/clear-highlights',
    )
    resp.raise_for_status()


def get_patient_variant_links(paper_id: int) -> list[PatientVariantLinkResp]:
    resp = requests.get(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/patient-variant-links'
    )
    resp.raise_for_status()
    return TypeAdapter(list[PatientVariantLinkResp]).validate_python(resp.json())


def get_phenotypes(paper_id: int, patient_id: int) -> list[PhenotypeResp]:
    resp = requests.get(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/patients/{patient_id}/phenotypes'
    )
    resp.raise_for_status()
    return TypeAdapter(list[PhenotypeResp]).validate_python(resp.json())


def get_paper_tasks(paper_id: int) -> list[TaskResp]:
    resp = requests.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/tasks')
    resp.raise_for_status()
    return TypeAdapter(list[TaskResp]).validate_python(resp.json())


def enqueue_paper_task(
    paper_id: int,
    task_type: TaskType,
    patient_id: int | None = None,
    variant_id: int | None = None,
    phenotype_id: int | None = None,
    skip_successors: bool = False,
) -> TaskResp:
    resp = requests.post(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/tasks',
        json=TaskCreateRequest(
            type=task_type,
            patient_id=patient_id,
            variant_id=variant_id,
            phenotype_id=phenotype_id,
            skip_successors=skip_successors,
        ).model_dump(),
    )
    resp.raise_for_status()
    return TaskResp.model_validate(resp.json())
