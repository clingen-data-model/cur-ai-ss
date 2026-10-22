import asyncio
import html
import json
import shutil
import tempfile
from enum import StrEnum
from io import BytesIO
from pathlib import Path

from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import (
    DocumentConverter,
    FormatOption,
    PdfFormatOption,
    WordFormatOption,
)
from docling_core.types.doc import (
    DoclingDocument,
    PictureItem,
    TableItem,
)
from docling_core.types.doc.page import TextCellUnit
from docling_parse.pdf_parser import DoclingPdfParser, PdfDocument
from pydantic import BaseModel
from xldown import excel_to_markdown

from lib.agents.table_correction_agent import correct_tables
from lib.misc.pdf import layout
from lib.misc.pdf.anchors import anchored_from_markdown, build_anchored, write_anchored
from lib.misc.pdf.paths import (
    document_image_path,
    document_images_dir,
    document_raw_path,
    document_success_path,
    document_table_image_path,
    document_table_markdown_path,
    document_tables_dir,
    document_words_json_path,
)
from lib.models import PaperDB
from lib.models.paper import FileFormat

IMAGE_RESOLUTION_SCALE = 4.0

# A multi-panel figure comes out of Docling whole rather than as its one
# best-scoring panel (see lib/misc/pdf/layout.py).
layout.install()


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


def _reset_dir(path: Path) -> None:
    """An empty directory: a re-parse never inherits the previous parse's
    tables, images or correction markers, whose Docling numbering may differ."""
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def _parse_xlsx_content(paper_id: int, content: bytes) -> None:
    """The XLSX supplement has no Docling document: convert it to markdown and
    tag that as it is (``anchored_from_markdown``)."""
    images_dir = document_images_dir(paper_id, supplement=True)
    _reset_dir(images_dir)

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
                        dest = document_image_path(paper_id, image_id, supplement=True)
                        shutil.copy2(src_img, dest)
                        # Absolute, rooted at CAA_ROOT, like the figure paths
                        # build_anchored prints for the main paper: the
                        # frontend rewrites an image src of that form to a
                        # URL, and only recognizes that form.
                        ref_map[f'{src_subdir}/{src_img.name}'] = str(dest)
                        image_id += 1

        for old_ref, new_ref in ref_map.items():
            md_text = md_text.replace(old_ref, new_ref)

    md, anchors = anchored_from_markdown(md_text, supplement=True)
    write_anchored(paper_id, md, anchors, supplement=True)


def write_tables_and_images(
    document: DoclingDocument, paper_id: int, *, supplement: bool = False
) -> None:
    """Crop every table and picture out of a parsed Docling document into the
    paper's tables/ and images/, keyed by Docling index -- the N of the
    table-N and figure-N anchors. A table gets Docling's own markdown beside
    its image, for the correction agent to judge."""
    tables_dir = document_tables_dir(paper_id, supplement)
    images_dir = document_images_dir(paper_id, supplement)
    _reset_dir(tables_dir)
    _reset_dir(images_dir)

    for element, _level in document.iterate_items():
        if isinstance(element, TableItem):
            index = int(element.self_ref.rsplit('/', 1)[1])
            document_table_markdown_path(paper_id, index, supplement).write_text(
                element.export_to_markdown(document)
            )
            if (table_image := element.get_image(document)) is not None:
                with open(
                    document_table_image_path(paper_id, index, supplement), 'wb'
                ) as fp:
                    table_image.save(fp, 'PNG')

        if isinstance(element, PictureItem):
            index = int(element.self_ref.rsplit('/', 1)[1])
            if (image := element.get_image(document)) is not None:
                with open(document_image_path(paper_id, index, supplement), 'wb') as fp:
                    image.save(fp, 'PNG')


async def parse_content(
    paper_id: int,
    force: bool = False,
    supplement_format: FileFormat | None = None,
) -> None:
    """Parse the paper (or its supplement) into documents/{id}/{main|supplement}.

    Reads raw.{pdf,docx,xlsx}; writes words.json, tables/, images/, and after
    table correction the anchored.md and anchors.json every agent and the
    highlighter read. The Docling document itself is not kept: a re-parse
    rebuilds everything from the raw file.
    """
    supplement = supplement_format is not None

    if not force and document_success_path(paper_id, supplement=supplement).exists():
        return

    raw = document_raw_path(
        paper_id,
        supplement=supplement,
        file_format=supplement_format.value if supplement_format else None,
    )
    if not raw.exists():
        return

    content = raw.read_bytes()

    if supplement_format == FileFormat.XLSX:
        _parse_xlsx_content(paper_id, content)
        document_success_path(paper_id, supplement=True).touch()
        return

    format_options: dict[InputFormat, FormatOption]
    if supplement_format == FileFormat.DOCX:
        format_options = {InputFormat.DOCX: WordFormatOption()}
    else:
        format_options = {
            InputFormat.PDF: PdfFormatOption(
                backend=PyPdfiumDocumentBackend,
                pipeline_options=PdfPipelineOptions(
                    images_scale=IMAGE_RESOLUTION_SCALE,
                    # Page renders are what the table and picture crops are
                    # cut from; they are not saved.
                    generate_page_images=True,
                    generate_picture_images=True,
                ),
            ),
        }

    doc_converter = DocumentConverter(format_options=format_options)

    document: DoclingDocument = doc_converter.convert(
        source=DocumentStream(name='content', stream=BytesIO(content)),
    ).document

    write_tables_and_images(document, paper_id, supplement=supplement)

    words_json = parse_words_json(BytesIO(content))
    with open(document_words_json_path(paper_id, supplement=supplement), 'w') as fp:
        json.dump([w.model_dump() for w in words_json], fp, indent=2)

    await correct_tables(paper_id, supplement=supplement)

    md, anchors = build_anchored(document, paper_id=paper_id, supplement=supplement)
    write_anchored(paper_id, md, anchors, supplement)
    document_success_path(paper_id, supplement=supplement).touch()
