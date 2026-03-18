import random

import requests
import streamlit as st

from lib.ui.api import get_http_error_detail, grobid_annotations, highlight_pdf

CURRENT_ANNOTATIONS_KEY = 'CURRENT_ANNOTATIONS_KEY'
HEADER_TABS = ['📄 PDF', '📝 Metadata', '👤 Patients', '🧬 Variants', '🔗 Occurrences']
HEADER_TABS_KEY = 'HEADER_TABS_KEY'

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


def get_gnomad_url(variant_id: str) -> str:
    return f'https://gnomad.broadinstitute.org/variant/{variant_id}?dataset=gnomad_r4'


def focus_and_switch_tab(
    paper_id: str, queries: list[str], image_ids: list[int], color: str
) -> None:
    try:
        current_annotations = grobid_annotations(
            paper_id,
            queries,
            image_ids,
            color,
        )
        st.toast('Found annotation for Focus - Zooming into the pdf!')
        st.session_state[HEADER_TABS_KEY] = HEADER_TABS[0]
        st.session_state[CURRENT_ANNOTATIONS_KEY] = current_annotations
    except requests.HTTPError as e:
        st.error(f'Failed to find Focus : {get_http_error_detail(e)}')


def highlight_evidence(
    paper_id: str, queries: list[str], image_ids: list[int], color: str
) -> None:
    try:
        highlight_pdf(
            paper_id,
            queries,
            image_ids,
            color,
        )
        st.toast('PDF Highlighted!')
    except requests.HTTPError as e:
        st.error(f'Failed to highlight: {get_http_error_detail(e)}')


def render_highlight_controls(
    paper_id: str,
    queries: list[str],
    color_key: str,
    button_key_prefix: str,
    disabled: bool = False,
    image_ids: list[int] | None = None,
) -> None:
    """Render color picker + Highlight + Focus & Switch Tab buttons."""
    if image_ids is None:
        image_ids = []
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
        args=(paper_id, queries, image_ids, color),
        disabled=disabled,
    )
    st.button(
        'Focus & Switch Tab',
        key=f'{button_key_prefix}-focus',
        type='secondary',
        on_click=focus_and_switch_tab,
        args=(paper_id, queries, image_ids, color),
        disabled=disabled,
    )


def render_evidence_controls(
    paper_id: str,
    label: str,
    evidence_context: str | None,
    reasoning: str | None,
    color_key: str,
    button_key_prefix: str,
) -> None:
    """Render popover + color picker + Highlight + Focus & Switch Tab buttons."""
    with st.container(
        horizontal=True, vertical_alignment='center', horizontal_alignment='right'
    ):
        with st.popover(label, type='tertiary', disabled=not evidence_context):
            st.markdown('**Evidence**: ' + (evidence_context or ''))
            st.markdown('**Reasoning**: ' + (reasoning or ''))
        render_highlight_controls(
            paper_id,
            [evidence_context] if evidence_context else [],
            color_key,
            button_key_prefix,
            disabled=not evidence_context,
        )
