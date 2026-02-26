from lib.agents.paper_extraction_agent import PaperExtractionOutput, TestingMethod
from lib.models import PaperResp


def paper_extraction_output_to_markdown(paper: PaperExtractionOutput) -> str:
    """
    Converts a PaperExtractionOutput Pydantic model to a Markdown string.
    """
    lines = []

    # Title
    if paper.title:
        lines.append(f'# {paper.title}\n')

    # Authors and Citation
    author_line = []
    if paper.first_author:
        author_line.append(f'**First Author:** {paper.first_author}')
    if paper.publication_year:
        author_line.append(f'**Publication Year:** {paper.publication_year}')
    if paper.journal_name:
        author_line.append(f'**Journal:** {paper.journal_name}')
    if author_line:
        lines.append(' | '.join(author_line) + '\n')

    # DOI / PMC / PMID
    id_lines = []
    if paper.doi:
        id_lines.append(f'**DOI:** [{paper.doi}](https://doi.org/{paper.doi})')
    if paper.pmcid:
        id_lines.append(
            f'**PMCID:** [{paper.pmcid}](https://www.ncbi.nlm.nih.gov/pmc/articles/{paper.pmcid}/)'
        )
    if paper.pmid:
        id_lines.append(
            f'**PMID:** [{paper.pmid}](https://pubmed.ncbi.nlm.nih.gov/{paper.pmid}/)'
        )
    if paper.paper_types:
        id_lines.append(
            f'**Paper Types:** '
            + ', '.join(pt.value.replace('_', ' ') for pt in paper.paper_types)
        )
    if id_lines:
        lines.append(' | '.join(id_lines) + '\n')

    # Abstract
    if paper.abstract:
        lines.append('## Abstract\n')
        lines.append(paper.abstract + '\n')

    # Testing Methods (optional addition)
    if paper.testing_methods:
        method_lines = [
            f'- **{method.value}**' + (f': {evidence}' if evidence else '')
            for method, evidence in zip(
                paper.testing_methods, paper.testing_methods_evidence
            )
        ]
        lines.append('## Testing Methods\n')
        lines.extend(method_lines)
        lines.append('')  # newline

    return '\n'.join(lines)


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
