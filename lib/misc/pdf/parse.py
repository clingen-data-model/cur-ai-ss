import html
import json
from io import BytesIO
from pathlib import Path

from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import (
    DocItemLabel,
    DoclingDocument,
    ImageRefMode,
    PictureItem,
    SectionHeaderItem,
    TableItem,
    TextItem,
)
from docling_core.types.doc.page import TextCellUnit
from docling_parse.pdf_parser import DoclingPdfParser, PdfDocument
from pydantic import BaseModel

from lib.misc.pdf.paths import (
    pdf_extraction_success_path,
    pdf_image_caption_path,
    pdf_image_path,
    pdf_images_dir,
    pdf_json_path,
    pdf_markdown_path,
    pdf_section_markdown_path,
    pdf_sections_dir,
    pdf_table_image_path,
    pdf_table_markdown_path,
    pdf_tables_dir,
    pdf_words_json_path,
)
from lib.models import PaperDB

IMAGE_RESOLUTION_SCALE = 4.0


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


def split_by_sections(
    document: DoclingDocument,
) -> tuple[list[tuple[str, str]], dict[int, str]]:
    sections: list[tuple[str, str]] = []
    image_captions: dict[int, str] = {}
    current_header = None
    current_text: list[str] = []

    for item, _ in document.iterate_items():
        if isinstance(item, SectionHeaderItem):
            # flush previous section
            if current_header is not None:
                sections.append((current_header.text, '\n\n'.join(current_text)))

            current_header = item
            current_text = []

        elif isinstance(item, TextItem):
            if item.label == DocItemLabel.CAPTION:
                if not item.parent:
                    continue
                if item.parent.cref.startswith('#/pictures/'):
                    image_captions[int(item.parent.cref.split('/')[-1])] = item.text
                elif item.parent.cref.startswith('#/tables/'):
                    # Skip table headers as they are included in table markdown.
                    continue
                else:
                    print(
                        f'Caption for non-image or non-table found {item.parent.cref}, violating assumption.'
                    )
            else:
                current_text.append(item.text)

    # flush final section
    if current_header is not None:
        sections.append((current_header.text, '\n\n'.join(current_text)))

    return sections, image_captions


def parse_content(paper_id: int, force: bool = False) -> None:
    if not force and pdf_extraction_success_path(paper_id).exists():
        return

    paper_db = PaperDB(id=paper_id).with_content()
    pdf_images_dir(paper_id).mkdir(parents=True, exist_ok=True)
    pdf_tables_dir(paper_id).mkdir(parents=True, exist_ok=True)
    pdf_sections_dir(paper_id).mkdir(parents=True, exist_ok=True)

    doc_converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                backend=PyPdfiumDocumentBackend,
                pipeline_options=PdfPipelineOptions(
                    images_scale=IMAGE_RESOLUTION_SCALE,
                    generate_page_images=True,
                    generate_picture_images=True,
                ),
            )
        }
    )

    document: DoclingDocument = doc_converter.convert(
        source=DocumentStream(name='content', stream=BytesIO(paper_db.content)),
    ).document

    document.save_as_markdown(
        pdf_markdown_path(paper_id),
        image_mode=ImageRefMode.REFERENCED,
        escape_html=False,
        escaping_underscores=False,
    )

    document.save_as_json(
        pdf_json_path(paper_id),
        image_mode=ImageRefMode.REFERENCED,
    )

    table_id, image_id = 0, 0

    for element, _level in document.iterate_items():
        if (
            isinstance(element, TableItem)
            and (table_image := element.get_image(document)) is not None
        ):
            with open(pdf_table_image_path(paper_id, table_id), 'wb') as fp:
                table_image.save(fp, 'PNG')

            with open(pdf_table_markdown_path(paper_id, table_id), 'w') as fp:
                fp.write(element.export_to_markdown(document))

            table_id += 1

        if (
            isinstance(element, PictureItem)
            and (image := element.get_image(document)) is not None
        ):
            with open(pdf_image_path(paper_id, image_id), 'wb') as fp:
                image.save(fp, 'PNG')

            image_id += 1

    words_json = parse_words_json(BytesIO(paper_db.content))

    with open(pdf_words_json_path(paper_id), 'w') as fp:
        json.dump([w.model_dump() for w in words_json], fp, indent=2)

    section_mds, image_captions = split_by_sections(document)

    for i, section_md in enumerate(section_mds):
        with open(pdf_section_markdown_path(paper_id, i), 'w') as fp:
            fp.write('## ' + section_md[0])
            fp.write('\n\n')
            fp.write(section_md[1])

    for i, caption in image_captions.items():
        with open(pdf_image_caption_path(paper_id, i), 'w') as fp:
            fp.write(caption)

    with open(pdf_extraction_success_path(paper_id), 'w') as fp:
        fp.write('')
