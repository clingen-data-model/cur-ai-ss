"""Turn an uploaded document into the artifacts a model cannot produce itself.

Extraction reads the PDF directly now, so this step no longer converts anything
to markdown. What it does produce is geometry and images: word positions for
highlighting evidence on the page, and figures for the pedigree pass and for
figure-derived evidence.

Two libraries, each for what it is good at:

- docling-parse gives word quads that follow rotated text, which matters because
  this corpus contains sideways tables. PyMuPDF's word boxes are axis-aligned
  and would draw upright rectangles over rotated words.
- PyMuPDF extracts embedded figures and their page rectangles.

The heavy docling converter is deliberately absent. It supplied page markdown,
table crops and table structure, none of which anything reads any more, and it
brought torch and torchvision with it for the privilege.
"""

import itertools
import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

import fitz
import mammoth
from docling_core.types.doc.page import TextCellUnit
from docling_parse.pdf_parser import DoclingPdfParser, PdfDocument
from pydantic import BaseModel
from xldown import excel_to_markdown

from lib.misc.pdf.paths import (
    pdf_extraction_success_path,
    pdf_figures_json_path,
    pdf_image_path,
    pdf_images_dir,
    pdf_markdown_path,
    pdf_raw_path,
    pdf_words_json_path,
)
from lib.models.paper import FileFormat


class Polygon(BaseModel):
    """Polygon with 4 corner coordinates (top-left, top-right, bottom-right, bottom-left)."""

    x0: float
    y0: float
    x1: float
    y1: float
    x2: float
    y2: float
    x3: float
    y3: float


class WordLoc(Polygon):
    page_idx: int
    word: str

    def to_polygon(self) -> Polygon:
        """Convert to a Polygon, discarding word-specific fields."""
        return Polygon(
            x0=self.x0,
            y0=self.y0,
            x1=self.x1,
            y1=self.y1,
            x2=self.x2,
            y2=self.y2,
            x3=self.x3,
            y3=self.y3,
        )


class FigureLoc(BaseModel):
    """An extracted figure and where it sits on the page.

    image_id indexes the figures this step wrote, in page order. It is the only
    figure numbering in the system: the extraction agent is shown these images
    and picks from them, rather than inventing an index it cannot know.
    """

    image_id: int
    page_idx: int
    x0: float
    y0: float
    x1: float
    y1: float
    width: int
    height: int


def parse_words_json(stream: BytesIO) -> list[WordLoc]:
    words_json = []
    parser = DoclingPdfParser()
    pdf_doc: PdfDocument = parser.load(path_or_stream=stream)
    for page_idx, pred_page in pdf_doc.iterate_pages():
        for word in pred_page.iterate_cells(unit_type=TextCellUnit.WORD):
            words_json.append(
                WordLoc(
                    page_idx=page_idx,
                    word=word.text,
                    x0=word.rect.r_x0,
                    y0=word.rect.r_y0,
                    x1=word.rect.r_x1,
                    y1=word.rect.r_y1,
                    x2=word.rect.r_x2,
                    y2=word.rect.r_y2,
                    x3=word.rect.r_x3,
                    y3=word.rect.r_y3,
                )
            )
    return words_json


def extract_text(stream: BytesIO) -> str:
    """Reconstruct the paper's text, page by page.

    Extraction reads the PDF directly, but the tasks that call tools -- PubMed
    lookup, MONDO linking, segregation scoring -- run through the agents
    framework and take text. This is what they read.

    Line cells come out in reading order; words hyphenated across a line break
    are rejoined, since a split "gene-\nspecific" otherwise reaches the model as
    two tokens that match nothing.
    """
    parser = DoclingPdfParser()
    pdf_doc: PdfDocument = parser.load(path_or_stream=stream)

    pages: list[str] = []
    for _, pred_page in pdf_doc.iterate_pages():
        lines = [c.text for c in pred_page.iterate_cells(unit_type=TextCellUnit.LINE)]
        joined: list[str] = []
        for line in lines:
            if joined and joined[-1].endswith('-'):
                joined[-1] = joined[-1][:-1] + line
            else:
                joined.append(line)
        pages.append('\n'.join(joined))

    return '\n\n'.join(pages)


# Journal banners and rules are extracted as images too. They are wide, short
# and never a figure anyone cites, so they are skipped rather than shown to the
# model as candidate pedigrees.
_MIN_FIGURE_PIXELS = 40_000
_MAX_FIGURE_ASPECT = 8.0


def _is_probably_a_figure(width: int, height: int) -> bool:
    if width * height < _MIN_FIGURE_PIXELS:
        return False
    long_side, short_side = max(width, height), min(width, height)
    return short_side > 0 and long_side / short_side <= _MAX_FIGURE_ASPECT


def extract_figures(
    paper_id: int, content: bytes, supplement: bool = False
) -> list[FigureLoc]:
    """Write each embedded figure to images/<id>.png and record where it sits."""
    figures: list[FigureLoc] = []
    image_id = 0

    with fitz.open(stream=content, filetype='pdf') as doc:
        for page_idx in range(doc.page_count):
            page = doc[page_idx]
            for info in page.get_image_info(xrefs=True):
                xref = info.get('xref')
                if not xref:
                    continue
                # Rendered through a Pixmap rather than written straight from
                # extract_image(): the embedded stream is often JPEG and
                # sometimes CMYK, and these are saved as .png.
                pixmap = fitz.Pixmap(doc, xref)
                if pixmap.n - pixmap.alpha >= 4:
                    pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
                width, height = pixmap.width, pixmap.height
                if not _is_probably_a_figure(width, height):
                    continue

                path = pdf_image_path(paper_id, image_id, supplement=supplement)
                pixmap.save(path)

                bbox = info.get('bbox') or (0.0, 0.0, 0.0, 0.0)
                figures.append(
                    FigureLoc(
                        image_id=image_id,
                        page_idx=page_idx,
                        x0=bbox[0],
                        y0=bbox[1],
                        x1=bbox[2],
                        y1=bbox[3],
                        width=width,
                        height=height,
                    )
                )
                image_id += 1

    return figures


def _parse_docx_content(paper_id: int, content: bytes) -> None:
    """Convert a DOCX supplement to markdown, saving its images alongside.

    Images are written to files and referenced, never inlined: mammoth
    base64-inlines them by default, which turned one 2.6 MB supplement into
    12.6 MB of text.
    """
    counter = itertools.count()

    @mammoth.images.img_element
    def save_image(image: Any) -> dict[str, str]:
        image_id = next(counter)
        path = pdf_image_path(paper_id, image_id, supplement=True)
        with image.open() as src:
            data = src.read()
        try:
            with fitz.open(stream=data) as doc:
                doc[0].get_pixmap().save(path)
        except Exception:
            # Not something fitz opens; keep the original bytes under the name
            # the markdown will reference.
            path.write_bytes(data)
        return {'src': f'images/{image_id}.png'}

    result = mammoth.convert_to_markdown(BytesIO(content), convert_image=save_image)
    pdf_markdown_path(paper_id, supplement=True).write_text(result.value)


def _parse_xlsx_content(paper_id: int, content: bytes) -> None:
    images_dir = pdf_images_dir(paper_id, supplement=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        xlsx_path = tmp_path / 'raw.xlsx'
        xlsx_path.write_bytes(content)

        excel_to_markdown(xlsx_path, tmp_path / 'out')

        md_text = (tmp_path / 'out' / 'output.md').read_text()

        image_id = 0
        ref_map: dict[str, str] = {}

        for src_subdir in ('charts', 'images'):
            src_dir = tmp_path / 'out' / src_subdir
            if src_dir.exists():
                for src_img in sorted(src_dir.iterdir()):
                    if src_img.suffix.lower() == '.png':
                        dest = pdf_image_path(paper_id, image_id, supplement=True)
                        shutil.copy2(src_img, dest)
                        ref_map[f'{src_subdir}/{src_img.name}'] = (
                            f'images/{image_id}.png'
                        )
                        image_id += 1

        for old_ref, new_ref in ref_map.items():
            md_text = md_text.replace(old_ref, new_ref)

        pdf_markdown_path(paper_id, supplement=True).write_text(md_text)


async def parse_content(
    paper_id: int,
    force: bool = False,
    supplement_format: FileFormat | None = None,
) -> None:
    supplement = supplement_format is not None

    if (
        not force
        and pdf_extraction_success_path(paper_id, supplement=supplement).exists()
    ):
        return

    raw = pdf_raw_path(
        paper_id,
        supplement=supplement,
        file_format=supplement_format.value if supplement_format else None,
    )
    if not raw.exists():
        return

    content = raw.read_bytes()
    pdf_images_dir(paper_id, supplement=supplement).mkdir(parents=True, exist_ok=True)

    if supplement_format == FileFormat.XLSX:
        _parse_xlsx_content(paper_id, content)
        pdf_extraction_success_path(paper_id, supplement=True).touch()
        return

    if supplement_format == FileFormat.DOCX:
        _parse_docx_content(paper_id, content)
        pdf_extraction_success_path(paper_id, supplement=True).touch()
        return

    figures = extract_figures(paper_id, content, supplement=supplement)
    pdf_figures_json_path(paper_id, supplement=supplement).write_text(
        '[' + ',\n'.join(f.model_dump_json() for f in figures) + ']'
    )

    pdf_markdown_path(paper_id, supplement=supplement).write_text(
        extract_text(BytesIO(content))
    )

    words = parse_words_json(BytesIO(content))
    pdf_words_json_path(paper_id, supplement=supplement).write_text(
        '[' + ',\n'.join(w.model_dump_json() for w in words) + ']'
    )

    pdf_extraction_success_path(paper_id, supplement=supplement).touch()
