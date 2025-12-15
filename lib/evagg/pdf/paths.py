import hashlib
from pathlib import Path

from lib.evagg.utils.environment import env


# NB: this could be cached, but given the small size of our pdfs it's likely not worth it.
def hash_pdf_bytes(pdf_bytes: bytes) -> str:
    h = hashlib.sha256()
    h.update(pdf_bytes)
    return h.hexdigest()


def pdf_dir(pdf_bytes: bytes) -> Path:
    pdf_id = hash_pdf_bytes(pdf_bytes)
    return Path(env.EXTRACTED_PDF_DIR) / pdf_id


def pdf_tables_dir(pdf_bytes: bytes) -> Path:
    return pdf_dir(pdf_bytes) / 'tables'


def pdf_images_dir(pdf_bytes: bytes) -> Path:
    return pdf_dir(pdf_bytes) / 'images'


def pdf_markdown_path(pdf_bytes: bytes) -> Path:
    return pdf_dir(pdf_bytes) / 'raw.md'


def pdf_json_path(pdf_bytes: bytes) -> Path:
    return pdf_dir(pdf_bytes) / 'raw.json'


def pdf_words_json_path(pdf_bytes: bytes) -> Path:
    return pdf_dir(pdf_bytes) / 'words.json'


def pdf_extraction_success_path(pdf_bytes: bytes) -> Path:
    return pdf_dir(pdf_bytes) / '_SUCCESS'


def pdf_image_path(
    pdf_bytes: bytes,
    image_id: int,
) -> Path:
    return pdf_images_dir(pdf_bytes) / f'{image_id}.png'


def pdf_table_image_path(
    pdf_bytes: bytes,
    table_id: int,
) -> Path:
    return pdf_tables_dir(pdf_bytes) / f'{table_id}.png'


def pdf_table_markdown_path(
    pdf_bytes: bytes,
    table_id: int,
) -> Path:
    return pdf_tables_dir(pdf_bytes) / f'{table_id}.md'
