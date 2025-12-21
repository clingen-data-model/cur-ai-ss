from lib.evagg.pdf.parse import parse_content


def test_convert_and_extract_creates_outputs(
    test_file_contents,
):
    content = test_file_contents('ACN3-7-1962.pdf', mode='rb')
    # run extraction (force=True to avoid cache short-circuiting)
    paper = parse_content(content, force=True)

    # ---- core outputs ----
    json_path = paper.pdf_json_path
    md_path = paper.pdf_markdown_path
    success_path = paper.pdf_extraction_success_path

    assert json_path.exists(), 'JSON output was not created'
    assert md_path.exists(), 'Markdown output was not created'
    assert success_path.exists(), 'Success marker file was not created'

    # ---- tables ----
    table_images = []
    table_markdowns = []

    table_id = 0
    while True:
        img = paper.pdf_table_image_path(table_id)
        md = paper.pdf_table_markdown_path(table_id)
        if not img.exists() and not md.exists():
            break
        if img.exists():
            table_images.append(img)
        if md.exists():
            table_markdowns.append(md)
        table_id += 1

    assert len(table_images) >= 1, 'No table images were extracted'
    assert len(table_markdowns) >= 1, 'No table markdown files were extracted'
    assert len(table_images) == len(table_markdowns), (
        'Table images and table markdown lengths should be equivalent'
    )

    # ---- pictures ----
    images = []
    image_id = 0
    while True:
        img = paper.pdf_image_path(image_id)
        if not img.exists():
            break
        images.append(img)
        image_id += 1

    assert len(images) >= 1, 'No pictures were extracted'

    # -- section markdowns ---
    sections = []
    section_id = 0
    while True:
        section_md = paper.pdf_section_markdown_path(section_id)
        if not section_md.exists():
            break
        sections.append(section_md)
        section_id += 1

    assert len(sections) >= 20, 'Not enough sections were extracted'

    with open(paper.pdf_section_markdown_path(section_id - 1), 'r') as f:
        assert '## Supporting Information' in f.read()
