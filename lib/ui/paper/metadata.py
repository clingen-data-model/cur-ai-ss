import streamlit as st

from lib.agents.paper_extraction_agent import PaperType
from lib.agents.patient_variant_linking_agent import TestingMethod
from lib.models import PaperResp, PipelineStatus
from lib.ui.api import get_paper_links
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
                pt
                for pt in paper_resp.paper_types
                if pt in {e.value for e in PaperType}
            ]
            if paper_resp.paper_types
            else [],
            key='paper-types',
        )
    )

    paper_resp.abstract = st.text_area('Abstract', paper_resp.abstract, height=200)


paper, paper_resp, center = render_paper_header()
with center:
    if paper_resp.pipeline_status not in {
        PipelineStatus.EXTRACTION_COMPLETED,
        PipelineStatus.LINKING_RUNNING,
        PipelineStatus.LINKING_FAILED,
        PipelineStatus.COMPLETED,
    }:
        st.write(f'{paper_resp.filename} not yet extracted...')
        st.stop()

    # Aggregate testing methods from links API when pipeline is completed
    if paper_resp.pipeline_status == PipelineStatus.COMPLETED:
        links = get_paper_links(paper_resp.id)
        methods: dict[str, str | None] = {}
        for link in links:
            for i, method in enumerate(link.testing_methods or []):
                if method == TestingMethod.Unknown.value:
                    continue
                if method not in methods:
                    evidence = (
                        link.testing_methods_evidence[i]
                        if link.testing_methods_evidence
                        and i < len(link.testing_methods_evidence)
                        else None
                    )
                    methods[method] = evidence
        if methods:
            paper_resp.testing_methods = list(methods.keys())
            paper_resp.testing_methods_evidence = [v or '' for v in methods.values()]

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
