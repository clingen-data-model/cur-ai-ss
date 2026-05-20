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


def pdf_tables_dir(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / 'tables'


def pdf_images_dir(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / 'images'


def pdf_sections_dir(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / 'sections'


def pdf_markdown_path(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / 'raw.md'


def pdf_json_path(paper_id: int, supplement: bool = False) -> Path:
    base = pdf_supplements_dir(paper_id) if supplement else pdf_dir(paper_id)
    return base / 'raw.json'


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


def pdf_section_markdown_path(
    paper_id: int, section_id: int, supplement: bool = False
) -> Path:
    return pdf_sections_dir(paper_id, supplement) / f'{section_id}.md'


def paper_section_classification_path(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'paper_section_classification.json'


def fulltext_md(paper_id: int, supplement_format: 'FileFormat | None' = None) -> str:
    main_md = pdf_markdown_path(paper_id).read_text()
    supplement_md = pdf_markdown_path(paper_id, supplement=True)
    if supplement_md.exists():
        supplement_header = SUPPLEMENTARY_MATERIAL_HEADER
        if supplement_format:
            supplement_header += f' ({supplement_format.value.upper()})'
        return (
            main_md
            + '\n\n---\n\n'
            + supplement_header
            + '\n\n'
            + supplement_md.read_text()
        )
    return main_md


def relevant_sections_md(
    paper_id: int, supplement_format: 'FileFormat | None' = None
) -> str:
    """Return paper markdown with irrelevant sections removed.

    Falls back to fulltext_md if section classification has not been run yet.
    Splices directly from raw.md: when a classified irrelevant section header is
    encountered, lines are skipped until the next classified relevant section header.
    Unclassified headings do not change skip state.
    """
    classification_path = paper_section_classification_path(paper_id)
    if not classification_path.exists():
        return fulltext_md(paper_id, supplement_format)

    data = json.loads(classification_path.read_text())
    classified: dict[str, bool] = {
        s['header'].lower(): s.get('relevant', True) for s in data.get('sections', [])
    }

    main_md = pdf_markdown_path(paper_id).read_text()
    lines = main_md.splitlines(keepends=True)
    result_lines: list[str] = []
    skip = False
    for line in lines:
        heading_match = re.match(r'^#{1,3} (.+)', line.rstrip())
        if heading_match:
            header_text = heading_match.group(1).strip().lower()
            if header_text in classified:
                skip = not classified[header_text]
        if not skip:
            result_lines.append(line)

    filtered_md = ''.join(result_lines)

    supplement_md = pdf_markdown_path(paper_id, supplement=True)
    if supplement_md.exists():
        supplement_header = SUPPLEMENTARY_MATERIAL_HEADER
        if supplement_format:
            supplement_header += f' ({supplement_format.value.upper()})'
        return (
            filtered_md
            + '\n\n---\n\n'
            + supplement_header
            + '\n\n'
            + supplement_md.read_text()
        )

    return filtered_md


def sections_md(paper_id: int) -> list[str]:
    sections = []
    for section_path in pdf_sections_dir(paper_id).iterdir():
        if section_path.suffix == '.md':
            with section_path.open('r') as f:
                sections.append(f.read())
    return sections


def tables_md(paper_id: int) -> list[str]:
    tables = []
    for table_path in pdf_tables_dir(paper_id).iterdir():
        if table_path.suffix == '.md':
            with table_path.open('r') as f:
                tables.append(f.read())
    return tables
