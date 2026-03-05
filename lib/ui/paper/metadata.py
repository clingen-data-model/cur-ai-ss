import json

import streamlit as st

from lib.models import PaperResp, PaperType
from lib.ui.helpers import paper_resp_to_markdown
from lib.ui.paper.header import render_paper_header


@st.fragment
def render_editable_paper_tab(
    paper_resp: PaperResp,
) -> None:
    paper_resp.title = st.text_input('Title', paper_resp.title)

    paper_resp.first_author = st.text_input('First Author', paper_resp.first_author)

    # Publication Year
    pub_year_input = st.text_input(
        'Publication Year',
        str(paper_resp.publication_year) if paper_resp.publication_year else '',
    )
    paper_resp.publication_year = (
        int(pub_year_input) if pub_year_input.isdigit() else None
    )

    paper_resp.journal_name = st.text_input('Journal Name', paper_resp.journal_name)

    paper_resp.paper_types = [
        PaperType(pt)
        for pt in st.pills(
            'Paper Types',
            options=[pt.value for pt in PaperType],
            selection_mode='multi',
            default=[pt.value for pt in paper_resp.paper_types]
            if paper_resp.paper_types
            else [],
            key='paper-types',
        )
    ]

    paper_resp.abstract = st.text_area('Abstract', paper_resp.abstract, height=200)


paper_resp, center = render_paper_header()
with center:
    if not paper_resp:
        st.write(f'{paper_resp.filename} not yet extracted...')
        st.stop()
    md_tab, editable_tab = st.tabs(['View', 'Edit'])
    with md_tab:
        st.markdown(paper_resp_to_markdown(paper_resp))
        st.download_button(
            label='Download JSON',
            data=paper_resp.model_dump_json(indent=2),
            file_name='metadata.json',
            mime='application/json',
        )
    with editable_tab:
        render_editable_paper_tab(paper_resp)
