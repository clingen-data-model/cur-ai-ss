import streamlit as st

from lib.agents.paper_extraction_agent import PaperType
from lib.agents.patient_variant_linking_agent import TestingMethod
from lib.models import PaperResp
from lib.ui.helpers import paper_resp_to_markdown
from lib.ui.paper.header import render_paper_header


@st.fragment
def render_editable_paper_extraction_tab(
    paper_resp: PaperResp,
) -> None:
    paper_resp.title = st.text_input('Title', paper_resp.title)

    paper_resp.first_author = st.text_input('First Author', paper_resp.first_author)

    # Publication Year
    pub_year_input = st.text_input(
        'Publication Year',
        str(paper_resp.pub_year) if paper_resp.pub_year else '',
    )
    paper_resp.pub_year = int(pub_year_input) if pub_year_input.isdigit() else None

    paper_resp.journal = st.text_input('Journal Name', paper_resp.journal)

    paper_resp.paper_types = list(
        st.pills(
            'Paper Types',
            options=[pt.value for pt in PaperType],
            selection_mode='multi',
            default=[
                pt for pt in paper_resp.paper_types if pt in {e.value for e in PaperType}
            ]
            if paper_resp.paper_types
            else [],
            key='paper-types',
        )
    )

    paper_resp.abstract = st.text_area('Abstract', paper_resp.abstract, height=200)

    paper_resp.testing_methods = list(
        st.pills(
            'Testing Methods',
            options=[tm.value for tm in TestingMethod],
            selection_mode='multi',
            default=[
                tm
                for tm in (paper_resp.testing_methods or [])
                if tm in {e.value for e in TestingMethod}
            ],
            key='testing-methods',
        )
    )

    paper_resp.testing_methods_evidence = [
        st.text_area(
            f'Evidence for {method}',
            value=(paper_resp.testing_methods_evidence or [''])[i]
            if paper_resp.testing_methods_evidence
            and i < len(paper_resp.testing_methods_evidence)
            else '',
            height=60,
            key=f'testing-method-evidence-{i}',
        )
        for i, method in enumerate(paper_resp.testing_methods or [])
    ]


paper, paper_resp, center = render_paper_header()
with center:
    if not paper_resp.title:
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
        render_editable_paper_extraction_tab(paper_resp)
