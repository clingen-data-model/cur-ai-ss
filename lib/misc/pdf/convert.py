"""The heavy half of PDF parsing: raw bytes in, a Docling document and word boxes out.

Everything that needs the ``docling`` package (torch, layout/table models, OCR)
lives here and nowhere else, so it can run somewhere other than the worker.
``lib.misc.pdf.parse`` only needs ``docling_core`` and calls ``convert_content``
for this step.
"""

from io import BytesIO

from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import (
    DocumentConverter,
    FormatOption,
    PdfFormatOption,
    WordFormatOption,
)
from docling_core.types.doc.page import TextCellUnit
from docling_parse.pdf_parser import DoclingPdfParser, PdfDocument

from lib.misc.pdf.convert_result import ConvertResult
from lib.misc.pdf.file_format import FileFormat
from lib.misc.pdf.words import WordLoc

IMAGE_RESOLUTION_SCALE = 4.0


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


def convert_content(
    content: bytes, supplement_format: FileFormat | None = None
) -> ConvertResult:
    """Run Docling over a PDF (or DOCX supplement) and extract its word boxes."""
    format_options: dict[InputFormat, FormatOption]
    if supplement_format == FileFormat.DOCX:
        format_options = {InputFormat.DOCX: WordFormatOption()}
    else:
        format_options = {
            InputFormat.PDF: PdfFormatOption(
                backend=PyPdfiumDocumentBackend,
                pipeline_options=PdfPipelineOptions(
                    images_scale=IMAGE_RESOLUTION_SCALE,
                    generate_page_images=True,
                    generate_picture_images=True,
                ),
            ),
        }

    document = (
        DocumentConverter(format_options=format_options)
        .convert(source=DocumentStream(name='content', stream=BytesIO(content)))
        .document
    )
    return ConvertResult(document=document, words=parse_words_json(BytesIO(content)))
