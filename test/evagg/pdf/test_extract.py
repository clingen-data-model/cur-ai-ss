from lib.evagg.pdf.extract import convert_and_extract
from lib.evagg.pdf.paths import (
    pdf_json_path,
    pdf_markdown_path,
    pdf_table_image_path,
    pdf_table_markdown_path,
    pdf_image_path,
    pdf_extraction_success_path,
)


def test_convert_and_extract_creates_outputs(
    test_file_contents,
):
    pdf_bytes = test_file_contents('ACN3-7-1962.pdf', mode='rb')
    # run extraction (force=True to avoid cache short-circuiting)
    convert_and_extract(pdf_bytes, force=True)

    # ---- core outputs ----
    json_path = pdf_json_path(pdf_bytes)
    md_path = pdf_markdown_path(pdf_bytes)
    success_path = pdf_extraction_success_path(pdf_bytes)

    assert json_path.exists(), 'JSON output was not created'
    assert md_path.exists(), 'Markdown output was not created'
    assert success_path.exists(), 'Success marker file was not created'

    # ---- tables ----
    table_images = []
    table_markdowns = []

    table_id = 0
    while True:
        img = pdf_table_image_path(pdf_bytes, table_id)
        md = pdf_table_markdown_path(pdf_bytes, table_id)
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
        img = pdf_image_path(pdf_bytes, image_id)
        if not img.exists():
            break
        images.append(img)
        image_id += 1

    assert len(images) >= 1, 'No pictures were extracted'
