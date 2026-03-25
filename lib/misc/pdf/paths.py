from pathlib import Path

from lib.core.environment import env


def pdf_dir(paper_id: int) -> Path:
    return env.extracted_pdf_dir / str(paper_id)


def pdf_raw_path(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'raw.pdf'


def pdf_thumbnail_path(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'thumbnail.png'


def pdf_tables_dir(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'tables'


def pdf_images_dir(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'images'


def pdf_sections_dir(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'sections'


def pdf_markdown_path(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'raw.md'


def pdf_json_path(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'raw.json'


def pdf_words_json_path(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'words.json'


def pdf_highlighted_path(paper_id: int) -> Path:
    return pdf_dir(paper_id) / 'highlighted.pdf'


def pdf_extraction_success_path(paper_id: int) -> Path:
    return pdf_dir(paper_id) / '_SUCCESS'


def pdf_image_path(paper_id: int, image_id: int) -> Path:
    return pdf_images_dir(paper_id) / f'{image_id}.png'


def pdf_image_caption_path(paper_id: int, image_id: int) -> Path:
    return pdf_images_dir(paper_id) / f'{image_id}.md'


def pdf_table_image_path(paper_id: int, table_id: int) -> Path:
    return pdf_tables_dir(paper_id) / f'{table_id}.png'


def pdf_table_markdown_path(paper_id: int, table_id: int) -> Path:
    return pdf_tables_dir(paper_id) / f'{table_id}.md'


def pdf_section_markdown_path(paper_id: int, section_id: int) -> Path:
    return pdf_sections_dir(paper_id) / f'{section_id}.md'


def fulltext_md(paper_id: int) -> str:
    with pdf_markdown_path(paper_id).open('r') as f:
        return f.read()


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
