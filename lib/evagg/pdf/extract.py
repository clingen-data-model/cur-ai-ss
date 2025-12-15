from io import BytesIO
from collections import namedtuple
import json

from docling_core.types.doc import DoclingDocument
from docling_core.types.doc import ImageRefMode, PictureItem, TableItem
from docling.datamodel.base_models import InputFormat
from docling.datamodel.base_models import DocumentStream
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc.page import TextCellUnit
from docling_parse.pdf_parser import DoclingPdfParser, PdfDocument

from lib.evagg.pdf.paths import (
    pdf_json_path,
    pdf_markdown_path,
    pdf_table_image_path,
    pdf_image_path,
    pdf_table_markdown_path,
    pdf_extraction_success_path,
    pdf_words_json_path,
    pdf_images_dir,
    pdf_tables_dir,
)

IMAGE_RESOLUTION_SCALE = 2.0

WordLoc = namedtuple(
    'WordLoc', ['page_i', 'word', 'x0', 'y0', 'x1', 'y1', 'x2', 'y2', 'x3', 'y3']
)


def parse_words_json(stream: BytesIO) -> list[WordLoc]:
    words_json = []
    parser = DoclingPdfParser()
    pdf_doc: PdfDocument = parser.load(path_or_stream=stream)
    for page_i, pred_page in pdf_doc.iterate_pages():
        for word in pred_page.iterate_cells(unit_type=TextCellUnit.WORD):
            words_json.append(
                WordLoc(
                    page_i,
                    word.text,
                    word.rect.r_x0,
                    word.rect.r_y0,
                    word.rect.r_x1,
                    word.rect.r_y1,
                    word.rect.r_x2,
                    word.rect.r_y2,
                    word.rect.r_x3,
                    word.rect.r_y3,
                )
            )
    return words_json


def convert_and_extract(pdf_bytes: bytes, force: bool = False) -> None:
    if (
        not force
        and pdf_extraction_success_path(
            pdf_bytes,
        ).exists()
    ):
        return
    pdf_images_dir(
        pdf_bytes,
    ).mkdir(parents=True, exist_ok=True)
    pdf_tables_dir(
        pdf_bytes,
    ).mkdir(parents=True, exist_ok=True)
    doc_converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=PdfPipelineOptions(
                    images_scale=IMAGE_RESOLUTION_SCALE,
                    generate_page_images=True,
                    generate_picture_images=True,
                )
            )
        }
    )
    # NB: name is a required field.  We "could" pass in uploaded filename here, I just thought it wasn't relevant at this time.
    document: DoclingDocument = doc_converter.convert(
        source=DocumentStream(name='uploaded_file', stream=BytesIO(pdf_bytes)),
    ).document
    document.save_as_markdown(
        pdf_markdown_path(pdf_bytes),
        image_mode=ImageRefMode.PLACEHOLDER,
    )
    document.save_as_json(
        pdf_json_path(pdf_bytes),
        image_mode=ImageRefMode.PLACEHOLDER,
    )
    table_id, image_id = 0, 0
    for element, _level in document.iterate_items():
        if (
            isinstance(element, TableItem)
            and (table_image := element.get_image(document)) is not None
        ):
            with open(
                pdf_table_image_path(
                    pdf_bytes,
                    table_id,
                ),
                'wb',
            ) as fp:
                table_image.save(fp, 'PNG')
            with open(
                pdf_table_markdown_path(
                    pdf_bytes,
                    table_id,
                ),
                'w',
                encoding='utf-8',
            ) as fp:
                fp.write(element.export_to_markdown(document))
            table_id += 1
        if (
            isinstance(element, PictureItem)
            and (image := element.get_image(document)) is not None
        ):
            with open(
                pdf_image_path(
                    pdf_bytes,
                    image_id,
                ),
                'wb',
            ) as fp:
                image.save(fp, 'PNG')
            image_id += 1

    words_json = parse_words_json(BytesIO(pdf_bytes))
    with open(
        pdf_words_json_path(
            pdf_bytes,
        ),
        'w',
        encoding='utf-8',
    ) as fp:
        json.dump(words_json, fp, indent=2)

    with open(
        pdf_extraction_success_path(
            pdf_bytes,
        ),
        'w',
        encoding='utf-8',
    ) as fp:
        fp.write('')
