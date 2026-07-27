import random
from datetime import datetime
from typing import Any
from urllib.parse import quote

import requests
import streamlit as st
from streamlit_pdf_viewer import pdf_viewer

from lib.misc.pdf.paths import pdf_highlighted_path
from lib.models.evidence_block import EvidenceBlock, HumanEvidenceBlock, ReasoningBlock
from lib.models.paper import PaperResp
from lib.tasks import TaskType
from lib.ui.api import (
    clear_highlights,
    enqueue_paper_task,
    get_http_error_detail,
    grobid_annotations,
    highlight_pdf,
)

CURRENT_ANNOTATIONS_KEY = 'CURRENT_ANNOTATIONS_KEY'
HEADER_TABS = [
    '📝 Metadata',
    '👤 Patients',
    '🧬 Variants',
    '🔗 Occurrences',
    '💬 Chat with Agent',
]
HEADER_TABS_KEY = 'HEADER_TABS_KEY'
HUMAN_EDIT_NOTE_DEFAULT = 'Reasoning behind the change...'
CHAT_FEATURE_GATE_TIME = datetime(2026, 5, 17, 12, 0, 0)


def render_rerun_popover(
    *,
    label: str,
    key_prefix: str,
    paper_id: int,
    task_type: TaskType,
    help: str,
    family_id: int | None = None,
    patient_id: int | None = None,
    variant_id: int | None = None,
    phenotype_id: int | None = None,
    container: Any = None,
) -> None:
    """Render a "re-run" control as a popover with an optional additional-context box.

    Mirrors the "Rerun Agents" popover: clicking opens a window with a free-text
    context field passed to the agent, plus a confirm button that enqueues the
    scoped task. ``container`` lets callers anchor the popover in a column.
    """
    # When anchored in a column, wrap in a right-aligned container so the
    # content-fit button hugs the right edge instead of floating left.
    popover_key = f'{key_prefix}-popover'
    host: Any
    if container is not None:
        with container:
            host = st.container(horizontal_alignment='right')
    else:
        host = st
    with host.popover(
        label, width='content', help=help, key=popover_key, on_change='rerun'
    ):
        context = st.text_area(
            'Additional context for agent',
            value='',
            placeholder='Enter any additional context or instructions for the agent (optional)',
            height=100,
            key=f'{key_prefix}-context',
        )

        def _on_confirm() -> None:
            try:
                enqueue_paper_task(
                    paper_id,
                    task_type,
                    family_id=family_id,
                    patient_id=patient_id,
                    variant_id=variant_id,
                    phenotype_id=phenotype_id,
                    additional_context=st.session_state.get(f'{key_prefix}-context')
                    or None,
                )
                st.toast('Task enqueued', icon=':material/check:')
                st.session_state[popover_key] = False
            except Exception as e:
                st.toast(f'Failed to enqueue task: {str(e)}', icon='❌')

        st.button(
            'Confirm',
            type='secondary',
            key=f'{key_prefix}-confirm',
            on_click=_on_confirm,
        )


def get_available_tabs(paper_resp: PaperResp) -> list[str]:
    """Get available tabs for a paper, conditionally excluding chat based on update time.

    The chat feature is only available for papers updated after CHAT_FEATURE_GATE_TIME.
    """
    tabs = [
        '📝 Metadata',
        '👤 Patients',
        '🧬 Variants',
        '🔗 Occurrences',
    ]
    if paper_resp.updated_at > CHAT_FEATURE_GATE_TIME:
        tabs.append('💬 Chat with Agent')
    return tabs


COLORS = [
    '#FFF59D',  # soft yellow
    '#FFE082',  # warm amber
    '#FFCC80',  # light orange
    '#FFAB91',  # soft coral
    '#F48FB1',  # light pink
    '#CE93D8',  # soft purple
    '#B39DDB',  # lavender
    '#9FA8DA',  # muted indigo
    '#90CAF9',  # light blue
    '#81D4FA',  # sky blue
    '#80DEEA',  # cyan
    '#A5D6A7',  # light green
    '#C5E1A5',  # lime green
    '#E6EE9C',  # pale lime
    '#D7CCC8',  # soft beige/gray
    # Neon-ish / bright additions
    '#FF3D00',  # neon red
    '#FF6D00',  # bright orange
    '#FFEA00',  # neon yellow
    '#00E676',  # bright green
    '#00B0FF',  # neon blue
    '#D500F9',  # neon magenta
    '#FF4081',  # bright pink
    '#18FFFF',  # cyan neon
    '#64DD17',  # lime neon
    '#FF9100',  # vivid orange
]


def get_clinvar_url(
    hgvs_g: str | None = None,
    hgvs_c: str | None = None,
    rsid: str | None = None,
) -> str | None:
    identifier = hgvs_g or hgvs_c or rsid
    if not identifier:
        return None
    encoded = quote(identifier)
    return f'https://www.ncbi.nlm.nih.gov/clinvar/?term={encoded}'


def get_gnomad_url(variant_id: str) -> str:
    return f'https://gnomad.broadinstitute.org/variant/{variant_id}?dataset=gnomad_r4'


def get_clingen_url(caid: str) -> str:
    return f'https://reg.clinicalgenome.org/redmine/projects/registry/genboree_registry/by_canonicalid?canonicalid={caid}'


@st.dialog(
    'Pdf Focus Modal',
    width='large',
    on_dismiss=lambda: st.session_state.pop(CURRENT_ANNOTATIONS_KEY),
)
def pdf_focus_modal() -> None:
    paper_resp = st.session_state['paper_resp']
    annotations = st.session_state.get(CURRENT_ANNOTATIONS_KEY, [])
    pdf_viewer(
        pdf_highlighted_path(paper_resp.id),
        width=1000,
        height=800,
        zoom_level=1.5,
        viewer_align='center',  # Center alignment
        show_page_separator=True,  # Show separators between pages
        annotations=[a.dict() for a in annotations],
        # NB: scroll_to_annotation does not support 0... which is the index if there
        # is only a single annotation.
        scroll_to_annotation=1 if len(annotations) > 1 else None,
        scroll_to_page=annotations[0].page if len(annotations) == 1 else None,
        render_text=True,
    )
    col1, col2 = st.columns(2)
    with col1:
        if st.button(
            'Clear Highlights', width='stretch', icon=':material/highlight_off:'
        ):
            clear_highlights(paper_resp.id)
            st.rerun()
    with col2:
        st.download_button(
            label='Download PDF',
            data=open(pdf_highlighted_path(paper_resp.id), 'rb').read(),
            icon=':material/download:',
            mime='application/pdf',
            width='stretch',
        )


def focus_and_show_dialog(
    paper_id: int,
    queries: list[str],
    image_ids: list[int],
    table_ids: list[int],
    color: str,
) -> None:
    try:
        current_annotations = grobid_annotations(
            paper_id,
            queries,
            image_ids,
            table_ids,
            color,
        )
        st.session_state[CURRENT_ANNOTATIONS_KEY] = current_annotations
        pdf_focus_modal()
    except requests.HTTPError as e:
        st.error(f'Failed to find Focus : {get_http_error_detail(e)}')


def highlight_evidence(
    paper_id: int,
    queries: list[str],
    image_ids: list[int],
    table_ids: list[int],
    color: str,
) -> None:
    try:
        highlight_pdf(
            paper_id,
            queries,
            image_ids,
            table_ids,
            color,
        )
        st.toast('PDF Highlighted!')
    except requests.HTTPError as e:
        st.error(f'Failed to highlight: {get_http_error_detail(e)}')


def render_highlight_controls(
    paper_id: int,
    blocks: list[EvidenceBlock[Any]],
    color_key: str,
    button_key_prefix: str,
    disabled: bool = False,
) -> None:
    """Render color picker + Highlight + Focus & Switch Tab buttons.

    Args:
        paper_id: Paper ID for highlighting/focusing.
        blocks: List of EvidenceBlocks containing quotes and evidence sources.
        color_key: Session state key for color picker.
        button_key_prefix: Prefix for highlight/focus button keys.
        disabled: Whether to disable the controls.
    """

    # Extract fields from all blocks, filtering out supplement evidence
    queries = [b.quote for b in blocks if b.quote and not b.is_supplement]
    image_ids = [
        b.image_id for b in blocks if b.image_id is not None and not b.is_supplement
    ]
    table_ids = [
        b.table_id for b in blocks if b.table_id is not None and not b.is_supplement
    ]
    if color_key not in st.session_state:
        st.session_state[color_key] = random.choice(COLORS)
    color = st.color_picker(
        'Choose Color', label_visibility='collapsed', key=color_key, disabled=disabled
    )
    has_highlightable_evidence = bool(queries or image_ids or table_ids)
    st.button(
        'Highlight',
        key=f'{button_key_prefix}-highlight',
        type='secondary',
        on_click=highlight_evidence,
        args=(paper_id, queries, image_ids, table_ids, color),
        disabled=disabled or not has_highlightable_evidence,
    )
    st.button(
        'Focus',
        key=f'{button_key_prefix}-focus',
        type='secondary',
        on_click=focus_and_show_dialog,
        args=(paper_id, queries, image_ids, table_ids, color),
        disabled=disabled or not has_highlightable_evidence,
    )


def render_evidence_controls(
    paper_id: int,
    label: str,
    color_key: str,
    button_key_prefix: str,
    block: EvidenceBlock[Any] | ReasoningBlock[Any] | None = None,
    human_edit_note_key: str | None = None,
    human_edit_note_value: str | None = None,
) -> str | None:
    """Render popover + color picker + Highlight + Focus & Switch Tab buttons.

    Args:
        paper_id: Paper ID for highlighting/focusing.
        block: EvidenceBlock or ReasoningBlock containing quote, reasoning, and evidence sources.
        label: Label for the popover button.
        color_key: Session state key for color picker.
        button_key_prefix: Prefix for highlight/focus button keys.
        human_edit_note_key: Session state key for human edit note text area.
        human_edit_note_value: Explicit curator note value to show, overriding
            ``block.human_edit_note``. Use when the note lives on a different
            field than ``block`` (e.g. one note shared across a list of
            blocks that don't carry a ``human_edit_note`` themselves).

    Returns:
        The edited human edit note value if present, otherwise None.
    """
    # Extract fields from block if provided
    quote: str | None = None
    reasoning: str | None = None
    human_edit_note: str | None = None
    if block is not None:
        reasoning = block.reasoning
        if hasattr(block, 'quote'):
            quote = block.quote
        if hasattr(block, 'human_edit_note'):
            human_edit_note = block.human_edit_note
    if human_edit_note_value is not None:
        human_edit_note = human_edit_note_value

    edited_note: str | None = None
    with st.container(
        horizontal=True, vertical_alignment='center', horizontal_alignment='right'
    ):
        with st.popover(
            label,
            type='tertiary',
            disabled=not quote and not reasoning and not human_edit_note,
        ):
            if quote:
                st.markdown('**Evidence**: ' + quote)
            st.markdown('**Reasoning**: ' + (reasoning or ''))
            # Show info message if evidence is from supplement
            if isinstance(block, EvidenceBlock) and block.is_supplement:
                st.info(
                    '📎 This evidence comes from a supplement. PDF highlighting is only available for main document evidence.'
                )
            if human_edit_note and human_edit_note_key:
                st.markdown('---')
                st.markdown('**✏️ Curator Note**')
                st.caption('Explain why this value was manually overridden.')
                edited_note = st.text_area(
                    'Curator Note',
                    label_visibility='collapsed',
                    value=human_edit_note,
                    key=human_edit_note_key,
                    height=20,
                    max_chars=120,
                )
                edited_by_name = getattr(block, 'edited_by_name', None)
                if edited_by_name:
                    edited_at = getattr(block, 'edited_at', None)
                    when = f' on {edited_at:%Y-%m-%d}' if edited_at else ''
                    st.caption(f'✏️ Edited by {edited_by_name}{when}')
        # Only pass EvidenceBlock to highlight controls (ReasoningBlock has no evidence sources)
        highlight_blocks = [block] if isinstance(block, EvidenceBlock) else []
        if highlight_blocks:
            render_highlight_controls(
                paper_id,
                blocks=highlight_blocks,
                color_key=color_key,
                button_key_prefix=button_key_prefix,
                disabled=not quote,
            )

    return edited_note
