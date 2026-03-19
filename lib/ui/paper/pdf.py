import streamlit as st
from streamlit_pdf_viewer import pdf_viewer

from lib.models import PaperResp
from lib.ui.api import clear_highlights
from lib.ui.paper.shared import CURRENT_ANNOTATIONS_KEY


def render_pdf_tab() -> None:
    paper_resp: PaperResp = st.session_state['paper_resp']
    pdf_viewer(
        paper_resp.pdf_highlighted_path,
        width=1000,
        height=800,
        zoom_level=1.5,
        viewer_align='center',  # Center alignment
        show_page_separator=True,  # Show separators between pages
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
            data=open(paper_resp.pdf_highlighted_path, 'rb').read(),
            icon=':material/download:',
            mime='application/pdf',
            width='stretch',
        )
