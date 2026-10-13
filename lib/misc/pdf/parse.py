import asyncio
import html
import json
import shutil
import tempfile
from enum import StrEnum
from pathlib import Path

from docling_core.types.doc import (
    DoclingDocument,
    ImageRefMode,
    PictureItem,
    TableItem,
)
from xldown import excel_to_markdown

from lib.agents.table_correction_agent import correct_tables
from lib.misc.pdf.anchors import anchored_from_markdown, build_anchored, write_anchored
from lib.misc.pdf.convert import convert_content
from lib.misc.pdf.convert_result import save_convert_result
from lib.misc.pdf.paths import (
    document_image_path,
    document_images_dir,
    document_raw_path,
    document_success_path,
    document_table_image_path,
    document_table_markdown_path,
    document_table_unrecovered_path,
    document_table_vision_markdown_path,
    document_tables_dir,
    document_words_json_path,
    pdf_extraction_success_path,
    pdf_image_path,
    pdf_images_dir,
    pdf_json_path,
    pdf_markdown_path,
    pdf_raw_path,
    pdf_table_image_path,
    pdf_table_markdown_path,
    pdf_table_unrecovered_path,
    pdf_table_vision_markdown_path,
    pdf_tables_dir,
    pdf_words_json_path,
)
from lib.models import PaperDB
from lib.models.paper import FileFormat


def _parse_xlsx_content(paper_id: int, content: bytes) -> None:
    images_dir = pdf_images_dir(paper_id, supplement=True)
    images_dir.mkdir(parents=True, exist_ok=True)

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
                        dest = pdf_image_path(paper_id, image_id, supplement=True)
                        shutil.copy2(src_img, dest)
                        # Absolute, matching the path docling itself writes
                        # for the main paper's images (see parse_content) --
                        # the frontend rewrites any image src rooted at
                        # CAA_ROOT to a URL, and only recognizes that form.
                        ref_map[f'{src_subdir}/{src_img.name}'] = str(dest)
                        image_id += 1

        for old_ref, new_ref in ref_map.items():
            md_text = md_text.replace(old_ref, new_ref)

        pdf_markdown_path(paper_id, supplement=True).write_text(md_text)

    write_anchored_xlsx(paper_id, md_text)


# --- the anchor-indexed document layout (documents/{id}/{main|supplement}) ----
#
# Written alongside extracted_pdfs/ by parse_content and, for papers parsed
# before it existed, by lib/bin/backfill_documents.py -- both through the two
# functions below, so the two paths cannot drift.


def _copy_if_exists(src: Path, dest: Path) -> None:
    if src.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def write_anchored_document(
    document: DoclingDocument,
    paper_id: int,
    *,
    supplement: bool = False,
    file_format: str | None = None,
) -> None:
    """Populate documents/{id}/{main|supplement} from a parsed Docling document.

    Tables and images are keyed by Docling index. The extracted_pdfs/ layout
    numbers them by a counter that only advances for items Docling could crop,
    so the correction agent's ``N.vision.md``/``N.unrecovered`` are
    re-keyed here by replaying that counter over the same items.
    """
    document_tables_dir(paper_id, supplement).mkdir(parents=True, exist_ok=True)
    document_images_dir(paper_id, supplement).mkdir(parents=True, exist_ok=True)

    _copy_if_exists(
        pdf_raw_path(paper_id, supplement=supplement, file_format=file_format),
        document_raw_path(paper_id, supplement, file_format),
    )
    _copy_if_exists(
        pdf_words_json_path(paper_id, supplement=supplement),
        document_words_json_path(paper_id, supplement),
    )

    old_table_id = 0
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
                _copy_if_exists(
                    pdf_table_vision_markdown_path(paper_id, old_table_id, supplement),
                    document_table_vision_markdown_path(paper_id, index, supplement),
                )
                _copy_if_exists(
                    pdf_table_unrecovered_path(paper_id, old_table_id, supplement),
                    document_table_unrecovered_path(paper_id, index, supplement),
                )
                old_table_id += 1

        if isinstance(element, PictureItem):
            index = int(element.self_ref.rsplit('/', 1)[1])
            if (image := element.get_image(document)) is not None:
                with open(document_image_path(paper_id, index, supplement), 'wb') as fp:
                    image.save(fp, 'PNG')

    md, anchors = build_anchored(document, paper_id=paper_id, supplement=supplement)
    write_anchored(paper_id, md, anchors, supplement)
    document_success_path(paper_id, supplement).touch()


def write_anchored_xlsx(paper_id: int, md_text: str) -> None:
    """The XLSX supplement has no Docling document: tag its markdown as it is."""
    supplement = True
    document_images_dir(paper_id, supplement).mkdir(parents=True, exist_ok=True)
    _copy_if_exists(
        pdf_raw_path(paper_id, supplement=True, file_format=FileFormat.XLSX.value),
        document_raw_path(paper_id, supplement, FileFormat.XLSX.value),
    )
    old_images = pdf_images_dir(paper_id, supplement)
    new_images = document_images_dir(paper_id, supplement)
    for image in sorted(old_images.glob('*.png')) if old_images.exists() else []:
        shutil.copy2(image, new_images / image.name)
    md, anchors = anchored_from_markdown(
        md_text.replace(str(old_images), str(new_images)), supplement=supplement
    )
    write_anchored(paper_id, md, anchors, supplement)
    document_success_path(paper_id, supplement).touch()


async def parse_content(
    paper_id: int,
    force: bool = False,
    supplement_format: FileFormat | None = None,
) -> None:
    supplement = supplement_format is not None

    if (
        not force
        and pdf_extraction_success_path(paper_id, supplement=supplement).exists()
    ):
        return

    raw = pdf_raw_path(
        paper_id,
        supplement=supplement,
        file_format=supplement_format.value if supplement_format else None,
    )
    if not raw.exists():
        return

    content = raw.read_bytes()

    if supplement_format == FileFormat.XLSX:
        _parse_xlsx_content(paper_id, content)
        pdf_extraction_success_path(paper_id, supplement=True).touch()
        return

    pdf_images_dir(paper_id, supplement=supplement).mkdir(parents=True, exist_ok=True)
    pdf_tables_dir(paper_id, supplement=supplement).mkdir(parents=True, exist_ok=True)

    converted = convert_content(content, supplement_format)
    document = converted.document

    document.save_as_markdown(
        pdf_markdown_path(paper_id, supplement=supplement),
        image_mode=ImageRefMode.REFERENCED,
        escape_html=False,
        escaping_underscores=False,
    )

    save_convert_result(
        converted,
        pdf_json_path(paper_id, supplement=supplement),
        pdf_words_json_path(paper_id, supplement=supplement),
    )

    table_id, image_id = 0, 0

    for element, _level in document.iterate_items():
        if (
            isinstance(element, TableItem)
            and (table_image := element.get_image(document)) is not None
        ):
            with open(
                pdf_table_image_path(paper_id, table_id, supplement=supplement), 'wb'
            ) as fp:
                table_image.save(fp, 'PNG')

            with open(
                pdf_table_markdown_path(paper_id, table_id, supplement=supplement), 'w'
            ) as fp:
                fp.write(element.export_to_markdown(document))

            table_id += 1

        if (
            isinstance(element, PictureItem)
            and (image := element.get_image(document)) is not None
        ):
            with open(
                pdf_image_path(paper_id, image_id, supplement=supplement), 'wb'
            ) as fp:
                image.save(fp, 'PNG')

            image_id += 1

    await correct_tables(paper_id, supplement=supplement)

    write_anchored_document(
        document,
        paper_id,
        supplement=supplement,
        file_format=supplement_format.value if supplement_format else None,
    )

    with open(pdf_extraction_success_path(paper_id, supplement=supplement), 'w') as fp:
        fp.write('')
