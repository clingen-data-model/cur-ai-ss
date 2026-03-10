import streamlit as st

from lib.models import PaperResp


def render_pdf_tab(paper_resp: PaperResp) -> None:
    st.pdf(paper_resp.pdf_highlighted_path)
    st.download_button(
        label='Download PDF',
        data=open(paper_resp.pdf_highlighted_path, 'rb').read(),
        icon=':material/download:',
        mime='application/pdf',
        width='stretch',
    )
