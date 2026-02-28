import json

import streamlit as st

from lib.agents.paper_extraction_agent import (
    PaperExtractionOutput,
    PaperType,
)
from lib.ui.helpers import paper_extraction_output_to_markdown
from lib.ui.paper.header import render_paper_header


@st.fragment
def render_editable_paper_extraction_tab(
    paper_extraction_output: PaperExtractionOutput,
) -> None:
    paper_extraction_output.title = st.text_input(
        'Title', paper_extraction_output.title
    )

    paper_extraction_output.first_author = st.text_input(
        'First Author', paper_extraction_output.first_author
    )

    # Publication Year
    pub_year_input = st.text_input(
        'Publication Year',
        str(paper_extraction_output.publication_year)
        if paper_extraction_output.publication_year
        else '',
    )
    paper_extraction_output.publication_year = (
        int(pub_year_input) if pub_year_input.isdigit() else None
    )

    paper_extraction_output.journal_name = st.text_input(
        'Journal Name', paper_extraction_output.journal_name
    )

    paper_extraction_output.paper_types = [
        PaperType(pt)
        for pt in st.pills(
            'Paper Types',
            options=[pt.value for pt in PaperType],
            selection_mode='multi',
            default=[pt.value for pt in paper_extraction_output.paper_types]
            if paper_extraction_output.paper_types
            else [],
            key='paper-types',
        )
    ]

    paper_extraction_output.abstract = st.text_area(
        'Abstract', paper_extraction_output.abstract, height=200
    )


paper, _, paper_extraction_output, center = render_paper_header()
with center:
    md_tab, editable_tab = st.tabs(['View', 'Edit'])
    with md_tab:
        st.markdown(paper_extraction_output_to_markdown(paper_extraction_output))
        st.download_button(
            label='Download JSON',
            data=paper_extraction_output.model_dump_json(indent=2),
            file_name='metadata.json',
            mime='application/json',
        )
    with editable_tab:
        render_editable_paper_extraction_tab(paper_extraction_output)
