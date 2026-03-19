from typing import Any

import streamlit as st

from lib.models import PaperResp, PaperType, PaperUpdateRequest
from lib.ui.api import get_http_error_detail, update_paper


def render_metadata_tab() -> None:
    paper_resp: PaperResp = st.session_state['paper_resp']
    if not paper_resp.title:
        st.write(f'{paper_resp.filename} not yet extracted...')
        st.stop()
    title = st.text_input('Title', paper_resp.title)
    first_author = st.text_input('First Author', paper_resp.first_author)
    publication_year = st.number_input(
        'Publication Year (leave blank if unknown)',
        min_value=1950,
        max_value=2030,
        value=paper_resp.publication_year,
        step=1,
        format='%d',
    )
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

    changes: dict[str, Any] = {}
    if title != paper_resp.title:
        changes['title'] = title
    if first_author != paper_resp.first_author:
        changes['first_author'] = first_author
    if publication_year != paper_resp.publication_year:
        changes['publication_year'] = publication_year
    if (journal_name or None) != paper_resp.journal_name:
        changes['journal_name'] = journal_name or None
    if paper_types != paper_resp.paper_types:
        changes['paper_types'] = paper_types
    if (abstract or None) != paper_resp.abstract:
        changes['abstract'] = abstract or None
    update_request = PaperUpdateRequest(**changes)

    if changes:
        try:
            st.session_state['paper_resp'] = update_paper(
                paper_id=paper_resp.id,
                update_request=update_request,
            )
            st.toast('Saved!', icon=':material/check:')
            st.rerun()
        except Exception as e:
            st.toast(f'Failed to save: {str(e)}', icon='❌')
