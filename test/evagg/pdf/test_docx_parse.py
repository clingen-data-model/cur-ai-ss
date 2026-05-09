from lib.misc.pdf.parse import parse_content
from lib.misc.pdf.paths import (
    pdf_extraction_success_path,
    pdf_images_dir,
    pdf_markdown_path,
    pdf_raw_path,
)
from lib.models.paper import FileFormat


def test_docx_with_image_extracts_markdown_and_images(mocked_root_dir, docx_with_image):
    paper_id = 1

    # Set up supplement directory with DOCX file
    pdf_raw_path(paper_id, supplement=True).parent.mkdir(parents=True, exist_ok=True)
    pdf_raw_path(paper_id, supplement=True).write_bytes(docx_with_image)

    # Parse the supplement as DOCX
    parse_content(paper_id, force=True, supplement_format=FileFormat.DOCX)

    # Verify markdown was created
    md_path = pdf_markdown_path(paper_id, supplement=True)
    assert md_path.exists(), 'Markdown was not created'

    markdown_content = md_path.read_text()
    assert 'Test Document with Image' in markdown_content
    assert 'Image caption text' in markdown_content

    # Verify success marker was created
    success_path = pdf_extraction_success_path(paper_id, supplement=True)
    assert success_path.exists(), 'Success marker was not created'

    # Verify images were extracted
    images_dir = pdf_images_dir(paper_id, supplement=True)
    assert images_dir.exists(), 'Images directory was not created'

    extracted_images = list(images_dir.glob('*.png'))
    assert len(extracted_images) >= 1, 'No images were extracted'


def test_docx_markdown_includes_image_references(mocked_root_dir, docx_with_image):
    paper_id = 2

    pdf_raw_path(paper_id, supplement=True).parent.mkdir(parents=True, exist_ok=True)
    pdf_raw_path(paper_id, supplement=True).write_bytes(docx_with_image)

    parse_content(paper_id, force=True, supplement_format=FileFormat.DOCX)

    markdown_content = pdf_markdown_path(paper_id, supplement=True).read_text()

    # Verify the markdown contains image references (paths to extracted images)
    # Mammoth converts images to relative paths like ![](word/media/image1.png)
    assert '![' in markdown_content or 'media' in markdown_content, (
        'Markdown does not contain image references'
    )
