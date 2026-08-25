"""The parse step produces geometry and images, not text.

Extraction reads the PDF itself now, so what this step owes the rest of the
system is what a model cannot produce: word positions to highlight evidence
with, and figures to show and to cite.
"""

import json

from PIL import Image

from lib.misc.pdf.parse import _is_probably_a_figure, parse_content
from lib.misc.pdf.paths import (
    fulltext_md,
    pdf_extraction_success_path,
    pdf_figures_json_path,
    pdf_image_path,
    pdf_markdown_path,
    pdf_raw_path,
    pdf_words_json_path,
)
from lib.models.paper import FileFormat


async def _parse(paper_id: int, content: bytes, supplement_format=None):
    path = pdf_raw_path(
        paper_id,
        supplement=supplement_format is not None,
        file_format=supplement_format.value if supplement_format else None,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    await parse_content(paper_id, force=True, supplement_format=supplement_format)


async def test_parse_writes_words_and_figures(test_file_contents, mocked_root_dir):
    content = test_file_contents('ACN3-7-1962.pdf', mode='rb')
    await _parse(1, content)

    assert pdf_extraction_success_path(1).exists()

    words = json.loads(pdf_words_json_path(1).read_text())
    assert words, 'no words extracted'
    first = words[0]
    # Quads, not boxes: eight coordinates, so rotated text stays rotated.
    for corner in ('x0', 'y0', 'x1', 'y1', 'x2', 'y2', 'x3', 'y3'):
        assert corner in first
    assert 'page_idx' in first and 'word' in first

    figures = json.loads(pdf_figures_json_path(1).read_text())
    for fig in figures:
        assert {'image_id', 'page_idx', 'x0', 'y0', 'x1', 'y1'} <= set(fig)


async def test_figures_are_real_pngs(test_file_contents, mocked_root_dir):
    """extract_image() hands back the embedded stream, often JPEG and sometimes
    CMYK. These are written as .png, so they go through a Pixmap first."""
    content = test_file_contents('ACN3-7-1962.pdf', mode='rb')
    await _parse(2, content)

    figures = json.loads(pdf_figures_json_path(2).read_text())
    for fig in figures:
        with Image.open(pdf_image_path(2, fig['image_id'])) as im:
            assert im.format == 'PNG'
            assert im.mode in ('RGB', 'RGBA', 'L')
            assert (im.width, im.height) == (fig['width'], fig['height'])


async def test_figure_ids_are_contiguous_from_zero(test_file_contents, mocked_root_dir):
    """The extraction agent picks a pedigree from this list by index, so the
    numbering has to be the one on disk, with no gaps where a banner was."""
    content = test_file_contents('ACN3-7-1962.pdf', mode='rb')
    await _parse(3, content)

    figures = json.loads(pdf_figures_json_path(3).read_text())
    assert [f['image_id'] for f in figures] == list(range(len(figures)))
    for fig in figures:
        assert pdf_image_path(3, fig['image_id']).exists()


def test_banners_are_not_offered_as_figures():
    """Journal headers extract as images too; they are wide, short and never cited."""
    assert not _is_probably_a_figure(1116, 39)  # a masthead rule
    assert not _is_probably_a_figure(1116, 105)  # a journal banner
    assert not _is_probably_a_figure(80, 80)  # an icon
    assert _is_probably_a_figure(1007, 898)  # a real figure panel
    assert _is_probably_a_figure(1400, 976)


async def test_docx_supplement_converts_without_inlining_images(
    docx_with_image, mocked_root_dir
):
    """mammoth base64-inlines images by default, which turned one 2.6 MB
    supplement into 12.6 MB of text."""
    await _parse(4, docx_with_image, supplement_format=FileFormat.DOCX)

    md = pdf_markdown_path(4, supplement=True).read_text()
    assert 'data:image' not in md
    # images are saved beside the markdown and referenced, not inlined
    assert 'images/0.png' in md
    assert pdf_image_path(4, 0, supplement=True).exists()
    assert fulltext_md(4, FileFormat.DOCX).endswith(md)


async def test_paper_text_is_reconstructed_for_the_tool_using_tasks(
    test_file_contents, mocked_root_dir
):
    """Extraction reads the PDF, but PubMed/MONDO/segregation take text."""
    content = test_file_contents('ACN3-7-1962.pdf', mode='rb')
    await _parse(5, content)

    text = fulltext_md(5)
    assert len(text) > 1000
    # words split across a line break are rejoined, not left as two tokens
    assert '-\n' not in text
