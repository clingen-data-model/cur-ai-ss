from lib.models import PaperResp


def paper_resp_to_markdown(paper_resp: PaperResp) -> str:
    """Render PaperResp metadata fields as markdown."""
    lines = []

    if paper_resp.title:
        lines.append(f'# {paper_resp.title}\n')

    author_line = []
    if paper_resp.first_author:
        author_line.append(f'**First Author:** {paper_resp.first_author}')
    if paper_resp.pub_year:
        author_line.append(f'**Publication Year:** {paper_resp.pub_year}')
    if paper_resp.journal:
        author_line.append(f'**Journal:** {paper_resp.journal}')
    if author_line:
        lines.append(' | '.join(author_line) + '\n')

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
            + ', '.join(pt.replace('_', ' ') for pt in paper_resp.paper_types)
        )
    if id_lines:
        lines.append(' | '.join(id_lines) + '\n')

    if paper_resp.abstract:
        lines.append('## Abstract\n')
        lines.append(paper_resp.abstract + '\n')

    if paper_resp.testing_methods:
        method_lines = []
        evidence = paper_resp.testing_methods_evidence or []
        for i, method in enumerate(paper_resp.testing_methods):
            ev = evidence[i] if i < len(evidence) else None
            method_lines.append(f'- **{method}**' + (f': {ev}' if ev else ''))
        lines.append('## Testing Methods\n')
        lines.extend(method_lines)
        lines.append('')

    return '\n'.join(lines)
