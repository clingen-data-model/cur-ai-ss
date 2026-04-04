import json
from typing import Optional

import requests
import streamlit as st
from pydantic import BaseModel, ValidationError

from lib.models import PaperResp
from lib.tasks import (
    TaskStatus,
    TaskType,
    get_status_badge_color,
    get_status_badge_icon,
    infer_paper_status,
    is_task_completed,
)
from lib.ui.api import (
    delete_paper,
    enqueue_paper_task,
    get_http_error_detail,
    get_paper,
)
from lib.ui.paper.metadata import render_metadata_tab
from lib.ui.paper.occurrences import render_patient_variant_occurrences_tab
from lib.ui.paper.patients import render_patients_tab
from lib.ui.paper.shared import CURRENT_ANNOTATIONS_KEY, HEADER_TABS, HEADER_TABS_KEY
from lib.ui.paper.variants import render_variants_tab

RERUN_POPOVER_STATE_KEY = 'RERUN_POPOVER_STATE_KEY'


class PaperQueryParams(BaseModel):
    paper_id: int
    patient_id: Optional[int] = None
    variant_id: Optional[int] = None
    tab_id: Optional[int] = None

    @classmethod
    def from_query_params(cls) -> 'PaperQueryParams':
        raw_params = {
            'paper_id': st.query_params.get('paper_id'),
            'patient_id': st.query_params.get('patient_id'),
            'variant_id': st.query_params.get('variant_id'),
            'tab_id': st.query_params.get('tab_id'),
        }

        if not raw_params['paper_id']:
            st.warning('No paper_id provided in URL.')
            st.stop()

        try:
            return cls(**raw_params)  # type: ignore
        except ValidationError:
            # If ints fail to parse, fall back to None instead of crashing
            return cls(
                paper_id=int(raw_params['paper_id']),
                patient_id=None,
                variant_id=None,
            )


def render_queue_tasks_fragment(paper_query_params: PaperQueryParams) -> None:
    rerun_mode = st.radio(
        'What would you like to rerun?',
        options=[
            'Full pipeline (initial extraction + linking)',
            'Linking only (reuse existing initial extraction)',
        ],
    )

    def on_confirm() -> None:
        try:
            task_type = (
                TaskType.PDF_PARSING
                if rerun_mode == 'Full pipeline (initial extraction + linking)'
                else TaskType.PHENOTYPE_EXTRACTION
            )
            enqueue_paper_task(
                paper_id=paper_query_params.paper_id,
                task_type=task_type,
            )
            st.toast('Task Queued', icon=':material/thumb_up:')
            st.session_state.RERUN_POPOVER_STATE_KEY = False
        except Exception as e:
            st.toast(f'Failed to enqueue task: {str(e)}', icon='❌')

    st.button('Confirm Rerun', type='secondary', on_click=on_confirm)


st.set_page_config(layout='wide')
paper_query_params = PaperQueryParams.from_query_params()
with st.spinner('Loading paper...'):
    try:
        if 'paper_resp' not in st.session_state:
            paper_resp: PaperResp = get_paper(paper_query_params.paper_id)
            if paper_resp is None:
                st.error(f'Failed to Fetch {paper_query_params.paper_id}')
                st.divider()
                st.stop()
            st.session_state['paper_resp'] = paper_resp
        else:
            paper_resp = st.session_state['paper_resp']
    except requests.HTTPError as e:
        st.error(f'Failed to load paper: {get_http_error_detail(e)}')
        st.stop()
    except Exception as e:
        st.error(str(e))
        st.stop()

left, center, right = st.columns([1, 10, 1])
with left:
    with st.container(horizontal=True, vertical_alignment='center'):
        st.page_link('dashboard.py', label='Dashboard', icon='🏠')
with center:
    if is_task_completed(paper_resp.tasks, TaskType.PAPER_METADATA):
        st.markdown(f'# {paper_resp.title}')
        parts = [f'{paper_resp.first_author} et al. {paper_resp.publication_year}']
        if paper_resp.pmid:
            parts.append(
                f'PMID: [{paper_resp.pmid}](https://pubmed.ncbi.nlm.nih.gov/{paper_resp.pmid}/)'
            )
        if paper_resp.pmcid:
            parts.append(
                f'PMCID: [{paper_resp.pmcid}](https://www.ncbi.nlm.nih.gov/pmc/articles/{paper_resp.pmcid}/)'
            )
        if paper_resp.journal_name:
            parts.append(paper_resp.journal_name)
        st.caption(' • '.join(parts))
    else:
        st.markdown(f'# {paper_resp.filename}')
    left, right = st.columns([6, 3])
    with left:
        with st.container(horizontal=True, vertical_alignment='center'):
            if paper_query_params.tab_id:
                default_tab = HEADER_TABS[paper_query_params.tab_id]
            elif paper_query_params.patient_id:
                default_tab = '👤 Patients'
            elif paper_query_params.variant_id:
                default_tab = '🧬 Variants'
            else:
                default_tab = '📝 Metadata'
            metadata_tab, patients_tab, variants_tab, occurrences_tab = st.tabs(
                HEADER_TABS,
                on_change='rerun',
                default=default_tab,
                key=HEADER_TABS_KEY,
            )
            with center:
                if metadata_tab.open:
                    render_metadata_tab()
                elif patients_tab.open:
                    render_patients_tab(paper_query_params.patient_id)
                elif variants_tab.open:
                    render_variants_tab(paper_query_params.variant_id)
                elif occurrences_tab.open:
                    render_patient_variant_occurrences_tab()

    with right:
        with st.container(
            horizontal=True,
            vertical_alignment='center',
            horizontal_alignment='center',
        ):
            status = infer_paper_status(paper_resp.tasks)
            st.badge(
                status,
                icon=get_status_badge_icon(paper_resp.tasks),
                color=get_status_badge_color(paper_resp.tasks),
            )
            with st.popover(
                '🔄 Rerun Agents',
                type='tertiary',
                on_change='rerun',
                disabled=any(t.status == TaskStatus.RUNNING for t in paper_resp.tasks),
                key=RERUN_POPOVER_STATE_KEY,
            ):
                render_queue_tasks_fragment(paper_query_params)
            if st.button('🗑️ Delete Paper', type='tertiary', width='content'):
                try:
                    delete_paper(paper_query_params.paper_id)
                    st.toast('Successfully deleted!', icon='🗑️')
                    st.switch_page('dashboard.py')
                except Exception as e:
                    st.toast(f'Failed to delete: {str(e)}', icon='❌')
