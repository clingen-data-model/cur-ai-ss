from pathlib import Path
from typing import TYPE_CHECKING

from lib.core.environment import env

if TYPE_CHECKING:
    from lib.models.paper import FileFormat

SUPPLEMENTARY_MATERIAL_HEADER = '# Supplementary Material'


def pdf_dir(paper_id: int) -> Path:
    return env.extracted_pdf_dir / str(paper_id)


def pdf_supplements_dir(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'supplements'


def snapshots_dir(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'snapshots'


def pdf_raw_path(
    paper_id: int, supplement: bool = False, file_format: str | None = None
) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    if supplement and file_format:
        return base / f'raw.{file_format}'
    return base / 'raw.pdf'


def pdf_thumbnail_path(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'thumbnail.png'


def pdf_tables_dir(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / 'tables'


def pdf_images_dir(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / 'images'


def pdf_markdown_path(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / 'raw.md'


def pdf_json_path(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / 'raw.json'


def pdf_words_json_path(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / 'words.json'


def pdf_extraction_success_path(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / '_SUCCESS'


def pdf_image_path(paper_id: int, image_id: int, supplement: bool = False) -> Path:
    return pdf_images_dir(paper_id, supplement) / f'{image_id}.png'


def pdf_table_image_path(
    paper_id: int, table_id: int, supplement: bool = False
) -> Path:
    return pdf_tables_dir(paper_id, supplement) / f'{table_id}.png'


def pdf_table_markdown_path(
    paper_id: int, table_id: int, supplement: bool = False
) -> Path:
    return pdf_tables_dir(paper_id, supplement) / f'{table_id}.md'


def pdf_table_vision_markdown_path(
    paper_id: int, table_id: int, supplement: bool = False
) -> Path:
    return pdf_tables_dir(paper_id, supplement) / f'{table_id}.vision.md'


def pdf_table_unrecovered_path(
    paper_id: int, table_id: int, supplement: bool = False
) -> Path:
    """Present iff the correction agent judged the table corrupt and could not
    rebuild it from the image. Symmetric with ``.vision.md``: that file present
    means corrected, this one present means unrecovered, neither means clean.
    """
    return pdf_tables_dir(paper_id, supplement) / f'{table_id}.unrecovered'


def paper_section_classification_path(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'paper_section_classification.json'


# --- Anchor-indexed document layout: {CAA_ROOT}/documents/{paper_id}/{main|supplement}
#
# Written side by side with the extracted_pdfs/ layout above while both exist.
# Tables and images here are keyed by their Docling index (#/tables/N,
# #/pictures/N), which is also the number in the anchor ids (table-N, figure-N)
# printed into anchored.md -- one numbering everywhere, assigned by Docling.


def document_dir(paper_id: int, supplement: bool = False) -> Path:
    return env.documents_dir / str(paper_id) / ('supplement' if supplement else 'main')


def document_raw_path(
    paper_id: int, supplement: bool = False, file_format: str | None = None
) -> Path:
    return document_dir(paper_id, supplement) / f'raw.{file_format or "pdf"}'


def document_words_json_path(paper_id: int, supplement: bool = False) -> Path:
    return document_dir(paper_id, supplement) / 'words.json'


def document_anchored_md_path(paper_id: int, supplement: bool = False) -> Path:
    return document_dir(paper_id, supplement) / 'anchored.md'


def document_anchors_path(paper_id: int, supplement: bool = False) -> Path:
    return document_dir(paper_id, supplement) / 'anchors.json'


def document_success_path(paper_id: int, supplement: bool = False) -> Path:
    return document_dir(paper_id, supplement) / '_SUCCESS'


def document_tables_dir(paper_id: int, supplement: bool = False) -> Path:
    return document_dir(paper_id, supplement) / 'tables'


def document_images_dir(paper_id: int, supplement: bool = False) -> Path:
    return document_dir(paper_id, supplement) / 'images'


def document_table_markdown_path(
    paper_id: int, table_index: int, supplement: bool = False
) -> Path:
    return document_tables_dir(paper_id, supplement) / f'{table_index}.md'


def document_table_image_path(
    paper_id: int, table_index: int, supplement: bool = False
) -> Path:
    return document_tables_dir(paper_id, supplement) / f'{table_index}.png'


def document_table_vision_markdown_path(
    paper_id: int, table_index: int, supplement: bool = False
) -> Path:
    return document_tables_dir(paper_id, supplement) / f'{table_index}.vision.md'


def document_table_unrecovered_path(
    paper_id: int, table_index: int, supplement: bool = False
) -> Path:
    return document_tables_dir(paper_id, supplement) / f'{table_index}.unrecovered'


def document_image_path(
    paper_id: int, picture_index: int, supplement: bool = False
) -> Path:
    return document_images_dir(paper_id, supplement) / f'{picture_index}.png'


# Deliberately asks for nothing the reader cannot do: the extraction agents have
# no tools, so telling them to check the table image would invite claiming an
# image they never saw -- the same confabulation this marker exists to prevent.
UNRECOVERED_TABLE_MARKER = (
    '**[EXTRACTION WARNING - TABLE {table_id}: this table could not be read '
    'reliably. The rows below are scrambled: cells may be missing, misaligned, '
    'or under the wrong header. Treat values here as unreliable and prefer any '
    'other source in the paper. Do NOT conclude that a value is absent from the '
    'paper because it is absent from this table -- report it as unreadable '
    'instead.]**'
)


def _supplement_block(paper_id: int, supplement_format: 'FileFormat | None') -> str:
    """The supplement's anchored text under the heading agents are told marks it.

    ``core_extraction_rules.py`` names this heading, so it must be emitted exactly.
    Empty string when the paper has no supplement.
    """
    path = document_anchored_md_path(paper_id, supplement=True)
    if not path.exists():
        return ''
    header = SUPPLEMENTARY_MATERIAL_HEADER
    if supplement_format:
        header += f' ({supplement_format.value.upper()})'
    return '\n\n---\n\n' + header + '\n\n' + path.read_text()


def fulltext_md(paper_id: int, supplement_format: 'FileFormat | None' = None) -> str:
    """The text agents read: the anchored main paper, then the supplement if any.

    ``anchored.md`` (see ``lib.misc.pdf.anchors``) is written after table
    correction, so it already carries the vision-rebuilt tables and the
    unrecovered-table marker; nothing is applied at read time. ``raw.md`` is a
    debugging artifact now and the agents never see it.
    """
    main = document_anchored_md_path(paper_id).read_text()
    return main + _supplement_block(paper_id, supplement_format)
