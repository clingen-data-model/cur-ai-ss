import random
from typing import Any
from urllib.parse import quote

import requests
import streamlit as st
from streamlit_pdf_viewer import pdf_viewer

from lib.misc.pdf.paths import pdf_highlighted_path
from lib.models.evidence_block import EvidenceBlock, HumanEvidenceBlock, ReasoningBlock
from lib.ui.api import (
    clear_highlights,
    get_http_error_detail,
    grobid_annotations,
    highlight_pdf,
)

CURRENT_ANNOTATIONS_KEY = 'CURRENT_ANNOTATIONS_KEY'
HEADER_TABS = ['📝 Metadata', '👤 Patients', '🧬 Variants', '🔗 Occurrences']
HEADER_TABS_KEY = 'HEADER_TABS_KEY'
HUMAN_EDIT_NOTE_DEFAULT = 'Edited by Human'

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
    color_key: str,
    button_key_prefix: str,
    block: EvidenceBlock[Any] | None = None,
    disabled: bool = False,
) -> None:
    """Render color picker + Highlight + Focus & Switch Tab buttons.

    Args:
        paper_id: Paper ID for highlighting/focusing.
        block: EvidenceBlock containing quote and evidence sources.
        color_key: Session state key for color picker.
        button_key_prefix: Prefix for highlight/focus button keys.
        disabled: Whether to disable the controls.
    """

    # Extract fields from block
    quote: str | None = None
    table_id: int | None = None
    image_id: int | None = None
    if block is not None:
        quote = block.quote
        table_id = block.table_id
        image_id = block.image_id

    queries = [quote] if quote else []
    image_ids = [image_id] if image_id is not None else []
    table_ids = [table_id] if table_id is not None else []
    if color_key not in st.session_state:
        st.session_state[color_key] = random.choice(COLORS)
    color = st.color_picker(
        'Choose Color', label_visibility='collapsed', key=color_key, disabled=disabled
    )
    st.button(
        'Highlight',
        key=f'{button_key_prefix}-highlight',
        type='secondary',
        on_click=highlight_evidence,
        args=(paper_id, queries, image_ids, table_ids, color),
        disabled=disabled,
    )
    st.button(
        'Focus',
        key=f'{button_key_prefix}-focus',
        type='secondary',
        on_click=focus_and_show_dialog,
        args=(paper_id, queries, image_ids, table_ids, color),
        disabled=disabled,
    )


def render_evidence_controls(
    paper_id: int,
    label: str,
    color_key: str,
    button_key_prefix: str,
    block: EvidenceBlock[Any] | ReasoningBlock[Any] | None = None,
    human_edit_note_key: str | None = None,
) -> str | None:
    """Render popover + color picker + Highlight + Focus & Switch Tab buttons.

    Args:
        paper_id: Paper ID for highlighting/focusing.
        block: EvidenceBlock or ReasoningBlock containing quote, reasoning, and evidence sources.
        label: Label for the popover button.
        color_key: Session state key for color picker.
        button_key_prefix: Prefix for highlight/focus button keys.
        human_edit_note_key: Session state key for human edit note text area.

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

    edited_note: str | None = None
    with st.container(
        horizontal=True, vertical_alignment='center', horizontal_alignment='right'
    ):
        with st.popover(
            label,
            type='tertiary',
            disabled=not quote and not reasoning and not human_edit_note,
        ):
            st.markdown('**Evidence**: ' + (quote or ''))
            st.markdown('**Reasoning**: ' + (reasoning or ''))
            if human_edit_note and human_edit_note_key:
                edited_note = st.text_area(
                    'Human Edit Note',
                    label_visibility='collapsed',
                    value=human_edit_note,
                    key=human_edit_note_key,
                    height=20,
                    max_chars=120,
                )
        # Only pass EvidenceBlock to highlight controls (ReasoningBlock has no evidence sources)
        highlight_block = block if isinstance(block, EvidenceBlock) else None
        render_highlight_controls(
            paper_id,
            block=highlight_block,
            color_key=color_key,
            button_key_prefix=button_key_prefix,
            disabled=not quote,
        )

    return edited_note
