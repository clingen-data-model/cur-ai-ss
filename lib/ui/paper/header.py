import json
import re
from typing import Optional

import requests
import streamlit as st
from pydantic import BaseModel, ValidationError

from lib.models import PaperResp
from lib.tasks import (
    InferredPaperStatus,
    TaskStatus,
    TaskType,
    get_all_successor_levels,
    get_status_badge_color,
    get_status_badge_icon,
    infer_paper_status,
    infer_paper_status_detail,
    is_task_completed,
)
from lib.ui.api import (
    delete_paper,
    enqueue_paper_task,
    get_curation_pptx,
    get_http_error_detail,
    get_paper,
    list_snapshots,
    reset_paper,
)
from lib.ui.paper.chat import render_chat_with_agent_tab
from lib.ui.paper.metadata import render_metadata_tab
from lib.ui.paper.occurrences import render_patient_variant_occurrences_tab
from lib.ui.paper.patients import render_patients_tab
from lib.ui.paper.shared import (
    CURRENT_ANNOTATIONS_KEY,
    HEADER_TABS_KEY,
    TAB_CHAT,
    TAB_METADATA,
    TAB_OCCURRENCES,
    TAB_PATIENTS,
    TAB_TASKS,
    TAB_VARIANTS,
    get_available_tabs,
)
from lib.ui.paper.tasks import render_tasks_tab
from lib.ui.paper.variants import render_variants_tab

RERUN_POPOVER_STATE_KEY = 'RERUN_POPOVER_STATE_KEY'
RESET_POPOVER_STATE_KEY = 'RESET_POPOVER_STATE_KEY'


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
    task_type = st.selectbox(
        'Select task to rerun:',
        options=[t for t in TaskType if t.value != 'General Paper Question'],
        format_func=lambda t: t.value,
    )

    st.caption(task_type.description)

    skip_successors = st.checkbox(
        'Skip successor tasks (run only this task)',
        value=False,
        help='When checked, successor tasks will NOT be automatically queued after this task completes',
    )

    additional_context = st.text_area(
        'Additional context for agent',
        value='',
        placeholder='Enter any additional context or instructions for the agent (optional)',
        height=100,
    )
    st.caption(
        'ℹ️ Context is only used for this task and will not be passed to successor tasks.'
    )

    # Show the full chain of successors only if not skipping them
    if not skip_successors:
        successor_levels = get_all_successor_levels(task_type)
        if successor_levels:
            st.markdown('**Will trigger:**')
            for i, level in enumerate(successor_levels, 1):
                level_text = ', '.join([t.value for t in level])
                indent = '  ' * i
                st.caption(f'{indent}→ {level_text}')
        else:
            st.caption('↳ Terminal task (no successors)')

    def on_confirm() -> None:
        try:
            enqueue_paper_task(
                paper_id=paper_query_params.paper_id,
                task_type=task_type,
                skip_successors=skip_successors,
                additional_context=additional_context or None,
            )
            st.toast('Task Queued', icon=':material/thumb_up:')
            st.session_state.RERUN_POPOVER_STATE_KEY = False
        except Exception as e:
            st.toast(f'Failed to enqueue task: {str(e)}', icon='❌')

    st.button('Confirm Rerun', type='secondary', on_click=on_confirm)


def render_reset_fragment(paper_query_params: PaperQueryParams) -> None:
    st.markdown(
        'Each time the extraction pipeline finishes, the extracted data '
        '(patients, variants, phenotypes, links, ...) is saved as a snapshot. '
        'Rerunning agents produces a new snapshot when the results change, so '
        'older ones stay available. Resetting restores the paper exactly as '
        'the chosen snapshot recorded it, discarding any manual edits and any '
        'agent results produced after it.'
    )
    try:
        snapshots = list_snapshots(paper_query_params.paper_id)
    except requests.HTTPError as e:
        st.caption(f'Failed to load snapshots: {get_http_error_detail(e)}')
        return
    if not snapshots:
        st.caption(
            'No extraction snapshots yet. A snapshot is written each time the '
            'extraction pipeline completes.'
        )
        return

    chosen = st.selectbox(
        'Restore snapshot:',
        options=snapshots,
        index=0,
        format_func=lambda s: f'{s.created_at:%Y-%m-%d %H:%M} UTC'
        + (f' — {s.description}' if s.description else '')
        + (f' — {s.model}' if s.model else '')
        + (' — current state' if s.matches_current else ''),
    )
    st.caption(
        '⚠️ Resetting cannot be undone. Task history reverts with the snapshot; '
        'chat history and PDF highlights are kept.'
    )

    def on_confirm() -> None:
        try:
            result = reset_paper(paper_query_params.paper_id, chosen.name)
            if result.changed:
                st.session_state.pop('paper_resp', None)
                st.session_state.pop('pptx_bytes', None)
                st.toast('Paper reset to extraction snapshot', icon='⏪')
            else:
                st.toast(
                    'Paper already matches this snapshot — nothing to reset',
                    icon='ℹ️',
                )
            st.session_state[RESET_POPOVER_STATE_KEY] = False
        except requests.HTTPError as e:
            st.toast(f'Failed to reset: {get_http_error_detail(e)}', icon='❌')

    st.button(
        'Reset paper',
        type='primary',
        on_click=on_confirm,
        disabled=chosen.matches_current,
        help='The paper already matches this snapshot — nothing to reset'
        if chosen.matches_current
        else None,
    )


def _strip_trailing_punctuation(text: str) -> str:
    """Remove trailing punctuation from text."""
    return re.sub(r'[.,;:!?]+$', '', text)


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

    # Generate PPTX on page load if paper is completed
    if (
        infer_paper_status(paper_resp.tasks) == InferredPaperStatus.COMPLETED
        and 'pptx_bytes' not in st.session_state
    ):
        try:
            st.session_state['pptx_bytes'] = get_curation_pptx(
                paper_query_params.paper_id
            )
        except Exception as e:
            st.session_state['pptx_bytes'] = None
            st.error(f'Failed to generate PPTX: {str(e)}')

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
        if paper_resp.gene_symbol:
            parts.append(f'🧬 {paper_resp.gene_symbol}')
        st.caption(' • '.join(parts))
    else:
        st.markdown(f'# {paper_resp.filename}')
    # Show warning if paper classifier ran and marked paper as irrelevant
    if (
        is_task_completed(paper_resp.tasks, TaskType.PAPER_CLASSIFIER)
        and paper_resp.is_paper_relevant is False
    ):
        reasoning = ''
        if paper_resp.section_classifications:
            relevance_block = paper_resp.section_classifications.get(
                'is_paper_relevant', {}
            )
            reasoning = relevance_block.get('reasoning', '')
        st.warning(
            f'**Paper Classification Alert**: This paper was classified as not relevant for extraction (no clear patient-variant pairs found). {reasoning} '
            'You can still process this paper using the **Rerun Agents** panel if needed, skipping the Paper Classification task.',
            icon='⚠️',
        )

    left, right = st.columns([5, 4])
    with left:
        with st.container(horizontal=True, vertical_alignment='center'):
            available_tabs = get_available_tabs(paper_resp)
            if paper_query_params.tab_id:
                default_tab = (
                    available_tabs[paper_query_params.tab_id]
                    if paper_query_params.tab_id < len(available_tabs)
                    else available_tabs[0]
                )
            elif paper_query_params.patient_id:
                default_tab = TAB_PATIENTS
            elif paper_query_params.variant_id:
                default_tab = TAB_VARIANTS
            else:
                default_tab = TAB_METADATA
            tabs = st.tabs(
                available_tabs,
                on_change='rerun',
                default=default_tab,
                key=HEADER_TABS_KEY,
            )
            # Resolve by label: the tab list is conditional, so positions shift.
            tab_by_label = dict(zip(available_tabs, tabs))

            def is_open(label: str) -> bool:
                tab = tab_by_label.get(label)
                return bool(tab and tab.open)

            with center:
                if is_open(TAB_METADATA):
                    render_metadata_tab()
                elif is_open(TAB_OCCURRENCES):
                    render_patient_variant_occurrences_tab()
                elif is_open(TAB_PATIENTS):
                    render_patients_tab(paper_query_params.patient_id)
                elif is_open(TAB_VARIANTS):
                    render_variants_tab(paper_query_params.variant_id)
                elif is_open(TAB_CHAT):
                    render_chat_with_agent_tab()
                elif is_open(TAB_TASKS):
                    render_tasks_tab()

    with right:
        with st.container(
            horizontal=True,
            vertical_alignment='center',
            horizontal_alignment='center',
        ):
            detail = infer_paper_status_detail(paper_resp.tasks)
            badge_text = detail
            st.badge(
                badge_text,
                icon=get_status_badge_icon(paper_resp.tasks),
                color=get_status_badge_color(paper_resp.tasks),
            )
            with st.popover(
                '🔄 Rerun Agents',
                type='tertiary',
                disabled=any(t.status == TaskStatus.RUNNING for t in paper_resp.tasks),
                key=RERUN_POPOVER_STATE_KEY,
                on_change='rerun',
            ):
                render_queue_tasks_fragment(paper_query_params)
            tasks_active = any(
                t.status in (TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING)
                for t in paper_resp.tasks
            )
            with st.popover(
                '⏪ Reset',
                type='tertiary',
                disabled=tasks_active,
                key=RESET_POPOVER_STATE_KEY,
                on_change='rerun',
                help=(
                    '⏳ Reset is disabled while extraction tasks are queued or '
                    'running — a task finishing mid-reset would overwrite the '
                    'restored data. Wait for the pipeline to finish (or fail).'
                    if tasks_active
                    else 'Restore the paper to a saved extraction snapshot'
                ),
            ):
                render_reset_fragment(paper_query_params)
            title = paper_resp.title or f'paper_{paper_query_params.paper_id}'
            clean_title = _strip_trailing_punctuation(title)
            st.download_button(
                '📊 Download PPTX',
                data=st.session_state.get('pptx_bytes') or b'',
                file_name=f'{clean_title}.pptx',
                mime='application/vnd.openxmlformats-officedocument.presentationml.presentation',
                type='tertiary',
                width='content',
                disabled=not st.session_state.get('pptx_bytes'),
                help='Enabled when paper extraction is completed',
            )
            if st.button('🗑️ Delete Paper', type='tertiary', width='content'):
                try:
                    delete_paper(paper_query_params.paper_id)
                    st.toast('Successfully deleted!', icon='🗑️')
                    st.switch_page('dashboard.py')
                except Exception as e:
                    st.toast(f'Failed to delete: {str(e)}', icon='❌')
