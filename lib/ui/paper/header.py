import json
import time
from typing import Optional

import requests
import streamlit as st
from pydantic import BaseModel, ValidationError

from lib.models import PaperResp, PaperUpdateRequest, PipelineStatus
from lib.ui.api import (
    delete_paper,
    get_http_error_detail,
    get_paper,
    update_paper,
)


class PaperQueryParams(BaseModel):
    paper_id: str
    patient_id: Optional[int] = None
    variant_id: Optional[int] = None

    @classmethod
    def from_query_params(cls) -> 'PaperQueryParams':
        raw_params = {
            'paper_id': st.query_params.get('paper_id'),
            'patient_id': st.query_params.get('patient_id'),
            'variant_id': st.query_params.get('variant_id'),
        }

        if not raw_params['paper_id']:
            st.warning('No paper_id provided in URL.')
            st.stop()

        try:
            return cls(**raw_params)  # type: ignore
        except ValidationError:
            # If ints fail to parse, fall back to None instead of crashing
            return cls(
                paper_id=raw_params['paper_id'],
                patient_id=None,
                variant_id=None,
            )


@st.fragment
def render_rerun_evagg_fragment(paper_query_params: PaperQueryParams) -> None:
    rerun_mode = st.radio(
        'What would you like to rerun?',
        options=[
            'Full pipeline (initial extraction + linking)',
            'Linking only (reuse existing initial extraction)',
        ],
    )
    prompt_override = st.text_area(
        'Optional override instructions for the backend agent:',
        placeholder='Give context to the agent about the mistake.',
    )
    confirm = st.button('Confirm Rerun', type='secondary')
    if confirm:
        try:
            update_paper(
                paper_id=paper_query_params.paper_id,
                update_request=PaperUpdateRequest(
                    pipeline_status=(
                        PipelineStatus.QUEUED
                        if rerun_mode == 'Full pipeline (initial extraction + linking)'
                        else PipelineStatus.EXTRACTION_COMPLETED
                    ),
                    prompt_override=prompt_override or None,
                ),
            )
            st.toast('EvAGG Job Queued', icon=':material/thumb_up:')
            st.rerun()
        except Exception as e:
            st.toast(f'Failed to requeue: {str(e)}', icon='❌')


def render_paper_header() -> tuple[PaperResp, st.delta_generator.DeltaGenerator]:
    st.set_page_config(layout='wide')
    paper_query_params = PaperQueryParams.from_query_params()
    with st.spinner('Loading paper...'):
        try:
            paper_resp: PaperResp = get_paper(paper_query_params.paper_id)
            if paper_resp is None:
                st.error(f'Failed to Fetch {paper_query_params.paper_id}')
                st.divider()
                st.stop()
                return
        except requests.HTTPError as e:
            st.error(f'Failed to load paper: {get_http_error_detail(e)}')
            st.stop()
            return
        except Exception as e:
            st.error(str(e))
            st.stop()
            return

    left, center, right = st.columns([1, 10, 1])
    with left:
        with st.container(horizontal=True, vertical_alignment='center'):
            st.page_link('dashboard.py', label='Dashboard', icon='🏠')
    with center:
        if paper_resp.pipeline_status in {
            PipelineStatus.EXTRACTION_COMPLETED,
            PipelineStatus.LINKING_RUNNING,
            PipelineStatus.LINKING_FAILED,
            PipelineStatus.COMPLETED,
        }:
            st.markdown(f'# {paper_resp.title}')
            parts = [f'{paper_resp.first_author} et al. {paper_resp.publication_year}']
            if paper_resp.pmid:
                parts.append(f'PMID: {paper_resp.pmid}')
            if paper_resp.journal_name:
                parts.append(paper_resp.journal_name)
            st.caption(' • '.join(parts))
        else:
            st.markdown(f'# {paper_resp.filename}')
        st.divider()
        left, right = st.columns([5, 3])
        with left:
            with st.container(horizontal=True, vertical_alignment='center'):
                PAPER_PAGES = [
                    ('📄 PDF', 'paper/pdf.py'),
                    ('📝 Paper Metadata', 'paper/metadata.py'),
                    ('👤 Patients', 'paper/patients.py'),
                    ('🧬 Variants', 'paper/variants.py'),
                ]
                for i, (label, page) in enumerate(PAPER_PAGES):
                    if st.button(label, type='tertiary', width='content'):
                        st.query_params['paper_id'] = paper_query_params.paper_id
                        st.switch_page(
                            page, query_params={'paper_id': paper_query_params.paper_id}
                        )
                    if i < len(PAPER_PAGES) - 1:
                        st.space('small')

        with right:
            with st.container(
                horizontal=True,
                vertical_alignment='center',
                horizontal_alignment='center',
            ):
                st.badge(
                    paper_resp.pipeline_status.value,
                    icon=paper_resp.pipeline_status.icon,
                    color=paper_resp.pipeline_status.color,
                )
                with st.popover(
                    '🔄 Rerun Extraction',
                    type='tertiary',
                    disabled=(
                        paper_resp.pipeline_status
                        in {
                            PipelineStatus.QUEUED,
                            PipelineStatus.EXTRACTION_RUNNING,
                            PipelineStatus.LINKING_RUNNING,
                        }
                    ),
                ):
                    render_rerun_evagg_fragment(paper_query_params)
                if st.button('🗑️ Delete Paper', type='tertiary', width='content'):
                    try:
                        delete_paper(paper_query_params.paper_id)
                        st.toast('Successfully deleted!', icon='🗑️')
                        st.switch_page('dashboard.py')
                    except Exception as e:
                        st.toast(f'Failed to delete: {str(e)}', icon='❌')

    return paper_resp, center
