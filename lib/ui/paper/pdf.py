import streamlit as st

from lib.ui.paper.header import render_paper_header

paper_resp, center = render_paper_header()
with center:
    st.pdf(paper_resp.pdf_raw_path)
    st.download_button(
        label='Download PDF',
        data=open(paper_resp.pdf_raw_path, 'rb').read(),
        icon=':material/download:',
        mime='application/pdf',
        width='stretch',
    )
