import json
import re
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


def pdf_raw_path(
    paper_id: int, supplement: bool = False, file_format: str | None = None
) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    if supplement and file_format:
        return base / f'raw.{file_format}'
    return base / 'raw.pdf'


def pdf_thumbnail_path(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'thumbnail.png'


def pdf_images_dir(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / 'images'


def pdf_markdown_path(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / 'raw.md'


def pdf_figures_json_path(paper_id: int, supplement: bool = False) -> Path:
    """Index of extracted figures: image_id, page and page rectangle."""
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / 'figures.json'


def pdf_words_json_path(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / 'words.json'


def pdf_highlighted_path(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'highlighted.pdf'


def pdf_extraction_success_path(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / '_SUCCESS'


def pdf_image_path(paper_id: int, image_id: int, supplement: bool = False) -> Path:
    return pdf_images_dir(paper_id, supplement) / f'{image_id}.png'


def pdf_image_caption_path(
    paper_id: int, image_id: int, supplement: bool = False
) -> Path:
    return pdf_images_dir(paper_id, supplement) / f'{image_id}.md'


def fulltext_md(paper_id: int, supplement_format: 'FileFormat | None' = None) -> str:
    """The paper's text, for the tasks that read text rather than the PDF.

    Reconstructed by the parse step from the PDF's own text layer. Extraction
    reads the PDF directly; this exists for the tool-using tasks that run
    through the agents framework.
    """
    main = pdf_markdown_path(paper_id)
    text = main.read_text() if main.exists() else ''

    supplement_md = pdf_markdown_path(paper_id, supplement=True)
    if not supplement_md.exists():
        return text

    header = SUPPLEMENTARY_MATERIAL_HEADER
    if supplement_format:
        header += f' ({supplement_format.value.upper()})'
    return f'{text}\n\n---\n\n{header}\n\n{supplement_md.read_text()}'
