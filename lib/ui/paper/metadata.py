import streamlit as st

from lib.models import PaperResp, PaperType, PaperUpdateRequest
from lib.ui.api import get_http_error_detail, update_paper


def paper_resp_to_markdown(paper_resp: PaperResp) -> str:
    """
    Converts a PaperExtractionOutput Pydantic model to a Markdown string.
    """
    lines = []

    # Title
    if paper_resp.title:
        lines.append(f'# {paper_resp.title}\n')

    # Authors and Citation
    author_line = []
    if paper_resp.first_author:
        author_line.append(f'**First Author:** {paper_resp.first_author}')
    if paper_resp.publication_year:
        author_line.append(f'**Publication Year:** {paper_resp.publication_year}')
    if paper_resp.journal_name:
        author_line.append(f'**Journal:** {paper_resp.journal_name}')
    if author_line:
        lines.append(' | '.join(author_line) + '\n')

    # Last Modified
    if paper_resp.last_modified:
        lines.append(
            f'**Last Modified:** {paper_resp.last_modified.strftime("%Y-%m-%d %H:%M:%S %Z")}\n'
        )

    # DOI / PMC / PMID
    id_lines = []
    if paper_resp.doi:
        id_lines.append(
            f'**DOI:** [{paper_resp.doi}](https://doi.org/{paper_resp.doi})'
        )
    if paper_resp.pmcid:
        id_lines.append(
            f'**PMCID:** [{paper_resp.pmcid}](https://www.ncbi.nlm.nih.gov/pmc/articles/{paper_resp.pmcid}/)'
        )
    if paper_resp.pmid:
        id_lines.append(
            f'**PMID:** [{paper_resp.pmid}](https://pubmed.ncbi.nlm.nih.gov/{paper_resp.pmid}/)'
        )
    if paper_resp.paper_types:
        id_lines.append(
            f'**Paper Types:** '
            + ', '.join(pt.value.replace('_', ' ') for pt in paper_resp.paper_types)
        )
    if id_lines:
        lines.append(' | '.join(id_lines) + '\n')

    # Abstract
    if paper_resp.abstract:
        lines.append('## Abstract\n')
        lines.append(paper_resp.abstract + '\n')

    return '\n'.join(lines)


@st.fragment
def render_editable_paper_tab(
    paper_resp: PaperResp,
) -> None:
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
    update_request = PaperUpdateRequest(
        title=title if title != paper_resp.title else None,
        first_author=first_author if first_author != paper_resp.first_author else None,
        publication_year=publication_year
        if publication_year != paper_resp.publication_year
        else None,
        journal_name=journal_name if journal_name != paper_resp.journal_name else None,
        paper_types=paper_types if paper_types != paper_resp.paper_types else None,
        abstract=abstract if abstract != paper_resp.abstract else None,
    )
    # Only call update if at least one field is not None
    if any(value is not None for value in update_request.model_dump().values()):
        try:
            update_paper(
                paper_id=paper_resp.id,
                update_request=update_request,
            )
            st.toast('Saved!', icon=':material/check:')
        except Exception as e:
            st.toast(f'Failed to save: {str(e)}', icon='❌')


def render_metadata_tab(paper_resp: PaperResp) -> None:
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
