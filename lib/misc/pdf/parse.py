import asyncio
import html
import json
import shutil
import tempfile
from enum import StrEnum
from io import BytesIO
from pathlib import Path

from docling_core.types.doc import (
    DoclingDocument,
    PictureItem,
    TableItem,
)
from docling_core.types.doc.page import TextCellUnit
from pydantic import BaseModel
from xldown import excel_to_markdown

from lib.agents.table_correction_agent import correct_tables
from lib.core.environment import env
from lib.misc.pdf.anchors import anchored_from_markdown, build_anchored, write_anchored
from lib.misc.pdf.paths import (
    IMAGE_RESOLUTION_SCALE,
    document_image_path,
    document_images_dir,
    document_raw_path,
    document_success_path,
    document_table_image_path,
    document_table_markdown_path,
    document_tables_dir,
    document_words_json_path,
)
from lib.misc.pdf.remote import attach_page_images, convert_pdf_remote
from lib.models import PaperDB
from lib.models.paper import FileFormat

# ``docling`` itself (the converter, its pipeline options, the backends and
# the layout override, which reaches into its post-processor) is imported
# where it is used, not here. Importing it loads transformers and torch,
# about 9 of the 22 seconds the API took to start on an e2-medium
# (2026-11-03), and the API never converts anything: with the parsing
# service configured the worker does not either, outside a DOCX supplement.
# ``docling_core`` (the document types) and ``docling_parse`` (the words
# file) are light by comparison and stay at the top.


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
    from docling_parse.pdf_parser import DoclingPdfParser, PdfDocument

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


def convert_locally(
    content: bytes, supplement_format: FileFormat | None = None
) -> DoclingDocument:
    """Run Docling's converter in this process on a PDF (or DOCX supplement)."""
    from docling.backend.docling_parse_backend import (
        ThreadedDoclingParseDocumentBackend,
    )
    from docling.datamodel.base_models import DocumentStream, InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import (
        DocumentConverter,
        FormatOption,
        PdfFormatOption,
        WordFormatOption,
    )

    from lib.misc.pdf import layout

    # A multi-panel figure comes out of Docling whole rather than as its one
    # best-scoring panel (see lib/misc/pdf/layout.py); idempotent.
    layout.install()

    format_options: dict[InputFormat, FormatOption]
    if supplement_format == FileFormat.DOCX:
        format_options = {InputFormat.DOCX: WordFormatOption()}
    else:
        format_options = {
            InputFormat.PDF: PdfFormatOption(
                # Docling's default backend. The pypdfium2 one used from
                # 2026-04 to 2026-11 reports whole lines as text cells, so
                # TableFormer put every row of a table in its first column
                # and the vision judge rebuilt 30 of the 31 tables of the
                # local papers from their images; docling-parse gives word
                # cells and the grids come out right (papers 106, 109, 113).
                backend=ThreadedDoclingParseDocumentBackend,
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

    return doc_converter.convert(
        source=DocumentStream(name='content', stream=BytesIO(content)),
    ).document


async def convert(
    content: bytes, supplement_format: FileFormat | None = None
) -> DoclingDocument:
    """The Docling document of the file: from the PDF parsing service when
    ``PDF_PARSING_SERVICE_URL`` names one (PDFs only; ``lib.misc.pdf.remote``),
    else from the converter in this process."""
    if (
        supplement_format != FileFormat.DOCX
        and env.PDF_PARSING_SERVICE_URL
        and env.PDF_PARSING_EXCHANGE_BUCKET
    ):
        return await convert_pdf_remote(
            content,
            base_url=env.PDF_PARSING_SERVICE_URL,
            bucket=env.PDF_PARSING_EXCHANGE_BUCKET,
        )
    return convert_locally(content, supplement_format)


async def write_parse_outputs(
    document: DoclingDocument,
    content: bytes,
    paper_id: int,
    *,
    supplement: bool = False,
    correct: bool = True,
) -> None:
    """Everything the parse leaves on disk, from the converted document:
    tables/ and images/, words.json, then (after table correction, unless
    ``correct`` is off) anchored.md, anchors.json and the _SUCCESS marker."""
    write_tables_and_images(document, paper_id, supplement=supplement)

    # A DOCX has no page geometry to place words on; docling-parse 7 raises on
    # anything but a PDF where older releases returned no pages.
    words_json = (
        [] if not content.startswith(b'%PDF') else parse_words_json(BytesIO(content))
    )
    with open(document_words_json_path(paper_id, supplement=supplement), 'w') as fp:
        json.dump([w.model_dump() for w in words_json], fp, indent=2)

    if correct:
        await correct_tables(paper_id, supplement=supplement)

    md, anchors = build_anchored(document, paper_id=paper_id, supplement=supplement)
    write_anchored(paper_id, md, anchors, supplement)
    document_success_path(paper_id, supplement=supplement).touch()


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

    document = await convert(content, supplement_format)
    # Table correction is for tables Docling rebuilt from a page's layout,
    # which can come out jumbled, and it recovers one from the table's image.
    # A Word table is read from the file's own table structure, so it is
    # exact and has no image: the judge could only mistake a good table for a
    # corrupted one and then fail the parse looking for a picture of it
    # (paper 146 on dev, PMID 38773012, 2026-11-11). XLSX never reaches here.
    await write_parse_outputs(
        document,
        content,
        paper_id,
        supplement=supplement,
        correct=supplement_format != FileFormat.DOCX,
    )
