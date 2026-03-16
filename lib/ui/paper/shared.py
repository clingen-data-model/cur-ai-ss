import requests
import streamlit as st

from lib.ui.api import get_http_error_detail, grobid_annotations

CURRENT_ANNOTATIONS_KEY = 'CURRENT_ANNOTATIONS_KEY'
HEADER_TABS = ['📄 PDF', '📝 Metadata', '👤 Patients', '🧬 Variants', '🔗 Occurrences']
HEADER_TABS_KEY = 'HEADER_TABS_KEY'


def get_gnomad_url(variant_id: str) -> str:
    return f'https://gnomad.broadinstitute.org/variant/{variant_id}?dataset=gnomad_r4'


def highlight_and_switch_tab(
    paper_id: str, queries: list[str], image_ids: list[int], color: str
) -> None:
    try:
        current_annotations = grobid_annotations(
            paper_id,
            queries,
            image_ids,
            color,
        )
        st.toast('PDF highlighted! Zooming to highlight.')
        st.session_state[HEADER_TABS_KEY] = HEADER_TABS[0]
        st.session_state[CURRENT_ANNOTATIONS_KEY] = current_annotations
    except requests.HTTPError as e:
        st.error(f'Failed to highlight: {get_http_error_detail(e)}')
