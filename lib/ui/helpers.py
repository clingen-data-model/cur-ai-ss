from lib.models import PaperResp


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
