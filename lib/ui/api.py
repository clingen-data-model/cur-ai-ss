import mimetypes
from typing import Any

import requests
import streamlit as st
import streamlit.runtime.uploaded_file_manager
from pydantic import TypeAdapter

from lib.core.environment import env
from lib.misc.pdf.highlight import GrobidAnnotation
from lib.models import (
    ChatMessageResp,
    FamilyResp,
    FamilyUpdateRequest,
    GeneResp,
    PaperResp,
    PaperUpdateRequest,
    PatientResp,
    PatientUpdateRequest,
    PatientVariantOccurrenceResp,
    PatientVariantOccurrenceUpdateRequest,
    PedigreeResp,
    PhenotypeResp,
    SegregationAnalysisResp,
    SegregationEvidenceUpdateRequest,
    TaskResp,
    UserResp,
    VariantResp,
    VariantUpdateRequest,
)
from lib.tasks import TaskCreateRequest, TaskType

# Session-state key holding the current user's JWT access token. Written by
# lib/ui/auth.py after login; read here to authenticate every API request.
AUTH_TOKEN_KEY = 'auth_token'


class _AuthSession(requests.Session):
    """A requests Session that attaches the logged-in user's bearer token.

    The token is read from st.session_state on *every* request rather than
    stored on the session object: Streamlit serves all browser sessions from a
    single process, so a token cached on a shared object would leak between
    users. st.session_state is per-session, so reading it per-call is safe.
    """

    def request(  # type: ignore[override]
        self, method: str | bytes, url: str | bytes, **kwargs: Any
    ) -> requests.Response:
        token = st.session_state.get(AUTH_TOKEN_KEY)
        if token:
            headers = dict(kwargs.pop('headers', None) or {})
            headers['Authorization'] = f'Bearer {token}'
            kwargs['headers'] = headers
        return super().request(method, url, **kwargs)


_session = _AuthSession()


def get_http_error_detail(e: requests.HTTPError) -> str:
    """Safely extract the 'detail' from an HTTPError response."""
    if e.response is not None:
        try:
            return e.response.json().get('detail', e.response.text)
        except ValueError:
            # Response is not JSON
            return e.response.text
    return str(e)


def login(email: str, password: str) -> str:
    """POST to /auth/login and return the access token."""
    resp = requests.post(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/auth/login',
        json={'email': email, 'password': password},
    )
    resp.raise_for_status()
    return resp.json()['access_token']


def get_me() -> UserResp:
    resp = _session.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/auth/me')
    resp.raise_for_status()
    return UserResp.model_validate(resp.json())


def register(
    email: str, first_name: str, last_name: str, description_of_use_case: str
) -> UserResp:
    resp = _session.post(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/auth/register',
        json={
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'description_of_use_case': description_of_use_case,
        },
    )
    resp.raise_for_status()
    return UserResp.model_validate(resp.json())


def change_password(current_password: str, new_password: str) -> UserResp:
    resp = _session.post(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/auth/change-password',
        json={
            'current_password': current_password,
            'new_password': new_password,
        },
    )
    resp.raise_for_status()
    return UserResp.model_validate(resp.json())


def get_papers() -> list[PaperResp]:
    resp = _session.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/papers')
    resp.raise_for_status()
    return TypeAdapter(list[PaperResp]).validate_python(resp.json())


def search_genes(prefix: str, limit: int = 10) -> list[GeneResp]:
    resp = _session.get(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/genes/search',
        params={'prefix': prefix, 'limit': str(limit)},
    )
    resp.raise_for_status()
    return TypeAdapter(list[GeneResp]).validate_python(resp.json())


def get_paper(paper_id: int) -> PaperResp:
    resp = _session.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}')
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
        supplement_mime = (
            mimetypes.guess_type(supplement_file.name)[0] or 'application/octet-stream'
        )
        files['supplement_file'] = (
            supplement_file.name,
            supplement_file.read(),
            supplement_mime,
        )

    resp = _session.put(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers',
        data={'gene_symbol': gene_symbol},
        files=files,
        # Content type is multipart/form-data
    )
    resp.raise_for_status()
    return PaperResp.model_validate(resp.json())


def update_paper(paper_id: int, update_request: PaperUpdateRequest) -> PaperResp:
    resp = _session.patch(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}',
        json=update_request.model_dump(mode='json', exclude_unset=True),
    )
    resp.raise_for_status()
    return PaperResp.model_validate(resp.json())


def delete_paper(paper_id: int) -> None:
    resp = _session.delete(
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
    resp = _session.post(
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
    resp = _session.post(
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
    resp = _session.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/patients')
    resp.raise_for_status()
    return TypeAdapter(list[PatientResp]).validate_python(resp.json())


def get_families(paper_id: int) -> list[FamilyResp]:
    resp = _session.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/families')
    resp.raise_for_status()
    return TypeAdapter(list[FamilyResp]).validate_python(resp.json())


def update_family(
    paper_id: int, family_id: int, update_request: FamilyUpdateRequest
) -> FamilyResp:
    resp = _session.patch(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/families/{family_id}',
        json=update_request.model_dump(mode='json', exclude_unset=True),
    )
    resp.raise_for_status()
    return FamilyResp.model_validate(resp.json())


def get_pedigree(paper_id: int) -> PedigreeResp | None:
    resp = _session.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/pedigree')
    resp.raise_for_status()
    data = resp.json()
    return PedigreeResp.model_validate(data) if data else None


def update_patient(
    paper_id: int, patient_id: int, update_request: PatientUpdateRequest
) -> PatientResp:
    resp = _session.patch(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/patients/{patient_id}',
        json=update_request.model_dump(mode='json', exclude_unset=True),
    )
    resp.raise_for_status()
    return PatientResp.model_validate(resp.json())


def get_variants(paper_id: int) -> list[VariantResp]:
    resp = _session.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/variants')
    resp.raise_for_status()
    return TypeAdapter(list[VariantResp]).validate_python(resp.json())


def update_variant(
    paper_id: int, variant_id: int, update_request: VariantUpdateRequest
) -> VariantResp:
    resp = _session.patch(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/variants/{variant_id}',
        json=update_request.model_dump(mode='json', exclude_unset=True),
    )
    resp.raise_for_status()
    return VariantResp.model_validate(resp.json())


def clear_highlights(paper_id: int) -> None:
    resp = _session.post(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/clear-highlights',
    )
    resp.raise_for_status()


def get_occurrences(
    paper_id: int,
) -> list[PatientVariantOccurrenceResp]:
    """Get all patient-variant occurrences for a paper."""
    resp = _session.get(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/occurrences'
    )
    resp.raise_for_status()
    return TypeAdapter(list[PatientVariantOccurrenceResp]).validate_python(resp.json())


def update_occurrence(
    paper_id: int,
    occurrence_id: int,
    update_request: PatientVariantOccurrenceUpdateRequest,
) -> PatientVariantOccurrenceResp:
    resp = _session.patch(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/occurrences/{occurrence_id}',
        json=update_request.model_dump(mode='json', exclude_unset=True),
    )
    resp.raise_for_status()
    return PatientVariantOccurrenceResp.model_validate(resp.json())


def get_variant_occurrences(
    paper_id: int, variant_id: int
) -> list[PatientVariantOccurrenceResp]:
    """Get all patient occurrences of a specific variant."""
    resp = _session.get(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/variants/{variant_id}/occurrences'
    )
    resp.raise_for_status()
    return TypeAdapter(list[PatientVariantOccurrenceResp]).validate_python(resp.json())


def get_patient_occurrences(
    paper_id: int, patient_id: int
) -> list[PatientVariantOccurrenceResp]:
    """Get all variant occurrences for a specific patient."""
    resp = _session.get(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/patients/{patient_id}/occurrences'
    )
    resp.raise_for_status()
    return TypeAdapter(list[PatientVariantOccurrenceResp]).validate_python(resp.json())


# Backward compatibility alias
def get_patient_variant_occurrences(
    paper_id: int,
) -> list[PatientVariantOccurrenceResp]:
    """Deprecated: use get_occurrences() instead."""
    return get_occurrences(paper_id)


def get_phenotypes(paper_id: int, patient_id: int) -> list[PhenotypeResp]:
    resp = _session.get(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/patients/{patient_id}/phenotypes'
    )
    resp.raise_for_status()
    return TypeAdapter(list[PhenotypeResp]).validate_python(resp.json())


def get_segregation_analysis(paper_id: int) -> list[SegregationAnalysisResp]:
    resp = _session.get(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/segregation-analysis'
    )
    resp.raise_for_status()
    return TypeAdapter(list[SegregationAnalysisResp]).validate_python(resp.json())


def update_segregation_evidence(
    paper_id: int, family_id: int, update_request: SegregationEvidenceUpdateRequest
) -> SegregationAnalysisResp:
    resp = _session.patch(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/segregation-analysis/{family_id}',
        json=update_request.model_dump(mode='json', exclude_unset=True),
    )
    resp.raise_for_status()
    return SegregationAnalysisResp.model_validate(resp.json())


def get_paper_tasks(paper_id: int) -> list[TaskResp]:
    resp = _session.get(f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/tasks')
    resp.raise_for_status()
    return TypeAdapter(list[TaskResp]).validate_python(resp.json())


def enqueue_paper_task(
    paper_id: int,
    task_type: TaskType,
    family_id: int | None = None,
    patient_id: int | None = None,
    variant_id: int | None = None,
    phenotype_id: int | None = None,
    skip_successors: bool = False,
    additional_context: str | None = None,
) -> list[TaskResp]:
    resp = _session.post(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/tasks',
        json=TaskCreateRequest(
            type=task_type,
            family_id=family_id,
            patient_id=patient_id,
            variant_id=variant_id,
            phenotype_id=phenotype_id,
            skip_successors=skip_successors,
            additional_context=additional_context,
        ).model_dump(),
    )
    resp.raise_for_status()
    return TypeAdapter(list[TaskResp]).validate_python(resp.json())


def get_curation_pptx(paper_id: int) -> bytes:
    resp = _session.get(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/curation-export'
    )
    resp.raise_for_status()
    return resp.content


def get_chat_messages(paper_id: int) -> list[dict[str, str]]:
    resp = _session.get(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/chat/messages'
    )
    resp.raise_for_status()
    return TypeAdapter(list[dict[str, str]]).validate_python(resp.json())


def init_chat_message(paper_id: int, message: str) -> tuple[list[dict[str, str]], bool]:
    """Initialize a chat turn (fast; returns the routing result).

    Returns ``(messages, queued_task)``. When ``queued_task`` is True the turn is
    terminal (a task was queued) and the caller must NOT call
    ``generate_chat_response``; otherwise generation still owes the answer.
    """
    resp = _session.post(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/chat/init',
        json={'message': message},
    )
    resp.raise_for_status()
    data = resp.json()
    return data['messages'], data['queued_task']


def generate_chat_response(
    paper_id: int, message: str | None = None
) -> list[dict[str, str]]:
    """Generate OpenAI response for the initialized conversation."""
    payload = {'message': message} if message else {}
    resp = _session.post(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/chat/generate',
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()


def clear_chat(paper_id: int) -> None:
    resp = _session.delete(
        f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/chat',
    )
    resp.raise_for_status()
