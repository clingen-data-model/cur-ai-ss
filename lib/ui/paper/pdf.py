import streamlit as st
from streamlit_pdf_viewer import pdf_viewer

from lib.models import PaperResp


def render_pdf_tab() -> None:
    paper_resp: PaperResp = st.session_state['paper_resp']
    pdf_viewer(
        paper_resp.pdf_highlighted_path,
        width=1000,
        height=1000,
        zoom_level=1.5,
        viewer_align='center',  # Center alignment
        show_page_separator=True,  # Show separators between pages
    )
    st.download_button(
        label='Download PDF',
        data=open(paper_resp.pdf_highlighted_path, 'rb').read(),
        icon=':material/download:',
        mime='application/pdf',
        width='stretch',
    )
