def paper_dict_to_markdown(paper: dict) -> str:
    """
    Converts a paper dictionary to a Markdown string.
    """
    lines = []

    # Title
    if 'title' in paper:
        lines.append(f'# {paper["title"]}\n')

    # Authors and Citation
    author_line = []
    if 'first_author' in paper:
        author_line.append(f'**First Author:** {paper["first_author"]}')
    if 'pub_year' in paper:
        author_line.append(f'**Year:** {paper["pub_year"]}')
    if 'journal' in paper:
        author_line.append(f'**Journal:** {paper["journal"]}')
    if author_line:
        lines.append(' | '.join(author_line) + '\n')

    # DOI / PMC / PMID
    id_lines = []
    if paper.get('doi'):
        id_lines.append(f'**DOI:** [{paper["doi"]}](https://doi.org/{paper["doi"]})')
    if paper.get('pmcid'):
        id_lines.append(
            f'**PMCID:** [{paper["pmcid"]}](https://www.ncbi.nlm.nih.gov/pmc/articles/{paper["pmcid"]}/)'
        )
    if paper.get('pmid'):
        id_lines.append(
            f'**PMID:** [{paper["pmid"]}]({paper.get("link", f"https://pubmed.ncbi.nlm.nih.gov/{paper['pmid']}/")})'
        )
    if id_lines:
        lines.append(' | '.join(id_lines) + '\n')

    # Open Access / License
    oa_lines = []
    if paper.get('OA'):
        oa_lines.append('✅ Open Access')
    if paper.get('license'):
        oa_lines.append(f'**License:** {paper["license"]}')
    if oa_lines:
        lines.append(' | '.join(oa_lines) + '\n')

    # Abstract
    if paper.get('abstract'):
        lines.append('## Abstract\n')
        lines.append(paper['abstract'] + '\n')

    return '\n'.join(lines)
