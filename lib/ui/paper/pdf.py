import streamlit as st
from streamlit_pdf_viewer import pdf_viewer

from lib.models import PaperResp
from lib.ui.paper.constants import CURRENT_ANNOTATIONS_KEY


def render_pdf_tab() -> None:
    paper_resp: PaperResp = st.session_state['paper_resp']
    annotations = st.session_state.get(CURRENT_ANNOTATIONS_KEY, [])
    pdf_viewer(
        paper_resp.pdf_highlighted_path,
        width=1000,
        height=800,
        zoom_level=1.5,
        viewer_align='center',  # Center alignment
        show_page_separator=True,  # Show separators between pages
        annotations=[a.dict() for a in annotations],
        scroll_to_annotation=1 if annotations else None,
    )
    st.download_button(
        label='Download PDF',
        data=open(paper_resp.pdf_highlighted_path, 'rb').read(),
        icon=':material/download:',
        mime='application/pdf',
        width='stretch',
    )
