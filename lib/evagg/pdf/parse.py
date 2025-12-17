from io import BytesIO
from collections import namedtuple
import json
from lib.evagg.types import Paper

from docling_core.types.doc import (
    DoclingDocument,
    ImageRefMode,
    PictureItem,
    TableItem,
    SectionHeaderItem,
    TextItem,
)
from docling.datamodel.base_models import InputFormat
from docling.datamodel.base_models import DocumentStream
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc.page import TextCellUnit
from docling_parse.pdf_parser import DoclingPdfParser, PdfDocument

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


def split_by_sections(document: DoclingDocument) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_header = None
    current_text: list[str] = []

    for (item, _) in document.iterate_items():
        if isinstance(item, SectionHeaderItem):
            # flush previous section
            if current_header is not None:
                sections.append((current_header.text, '\n\n'.join(current_text)))

            current_header = item
            current_text = []

        elif isinstance(item, TextItem):
            current_text.append(item.text)

    # flush final section
    if current_header is not None:
        sections.append((current_header.text, '\n\n'.join(current_text)))

    return sections



def parse_content(content: bytes, force: bool = False) -> Paper:
    paper = Paper.from_content(content)
    if not force and paper.pdf_extraction_success_path.exists():
        return paper
    paper.pdf_images_dir.mkdir(parents=True, exist_ok=True)
    paper.pdf_tables_dir.mkdir(parents=True, exist_ok=True)
    paper.pdf_sections_dir.mkdir(parents=True, exist_ok=True)
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
        source=DocumentStream(name='content', stream=BytesIO(paper.content)),
    ).document
    document.save_as_markdown(
        paper.pdf_markdown_path,
        image_mode=ImageRefMode.PLACEHOLDER,
    )
    document.save_as_json(
        paper.pdf_json_path,
        image_mode=ImageRefMode.PLACEHOLDER,
    )
    table_id, image_id = 0, 0
    for element, _level in document.iterate_items():
        if (
            isinstance(element, TableItem)
            and (table_image := element.get_image(document)) is not None
        ):
            with open(
                paper.pdf_table_image_path(
                    table_id,
                ),
                'wb',
            ) as fp:
                table_image.save(fp, 'PNG')
            with open(
                paper.pdf_table_markdown_path(
                    table_id,
                ),
                'w',
            ) as fp:
                fp.write(element.export_to_markdown(document))
            table_id += 1
        if (
            isinstance(element, PictureItem)
            and (image := element.get_image(document)) is not None
        ):
            with open(
                paper.pdf_image_path(
                    image_id,
                ),
                'wb',
            ) as fp:
                image.save(fp, 'PNG')
            image_id += 1

    words_json = parse_words_json(BytesIO(paper.content))
    with open(
        paper.pdf_words_json_path,
        'w',
    ) as fp:
        json.dump(words_json, fp, indent=2)

    section_mds: list[tuple[str, str]] = split_by_sections(document)
    for i, section_md in enumerate(section_mds):
        with open(
            paper.pdf_section_markdown_path(i),
            'w',
        ) as fp:
            fp.write('## ' + section_md[0])
            fp.write('\n\n')
            fp.write(section_md[1])

    with open(
        paper.pdf_extraction_success_path,
        'w',
    ) as fp:
        fp.write('')

    return paper
