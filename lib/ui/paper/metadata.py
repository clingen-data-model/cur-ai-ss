import streamlit as st

from lib.models import PaperResp, PaperType, PaperUpdateRequest
from lib.ui.api import get_http_error_detail, update_paper
from lib.ui.helpers import paper_resp_to_markdown
from lib.ui.paper.header import render_paper_header


@st.fragment
def render_editable_paper_tab(
    paper_resp: PaperResp,
) -> None:
    title = st.text_input('Title', paper_resp.title)
    first_author = st.text_input('First Author', paper_resp.first_author)

    # Publication Year
    pub_year_input = st.text_input(
        'Publication Year',
        str(paper_resp.publication_year) if paper_resp.publication_year else '',
    )
    paper_resp.publication_year = (
        int(pub_year_input) if pub_year_input.isdigit() else None
    )
    publication_year = int(pub_year_input) if pub_year_input.isdigit() else None
    journal_name = st.text_input('Journal Name', paper_resp.journal_name)

    # Paper Types
    selected_values = st.pills(
        'Paper Types',
        options=[pt.value for pt in PaperType],
        selection_mode='multi',
        default=[pt.value for pt in paper_resp.paper_types]
        if paper_resp.paper_types
        else [],
        key='paper-types',
    )
    # Enforce max 2 choices
    if len(selected_values) > 2:
        st.warning('Please select only **two** paper types.')
        selected_values = selected_values[:2]  # automatically keep the first two
    paper_types = [PaperType(pt) for pt in selected_values]

    abstract = st.text_area('Abstract', paper_resp.abstract, height=200)
    if (
        title != paper_resp.title
        or first_author != paper_resp.first_author
        or publication_year != paper_resp.publication_year
        or journal_name != paper_resp.journal_name
        or paper_types != paper_resp.paper_types
        or abstract != paper_resp.abstract
    ):
        try:
            update_paper(
                paper_id=paper_resp.id,
                update_request=PaperUpdateRequest(
                    title=title,
                    first_author=first_author,
                    publication_year=publication_year,
                    journal_name=journal_name,
                    paper_types=paper_types,
                    abstract=abstract,
                ),
            )
            st.toast('Saved!', icon=':material/check:')
        except Exception as e:
            st.toast(f'Failed to save: {str(e)}', icon='❌')


paper_resp, center = render_paper_header()
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
        render_editable_paper_tab(paper_resp)
