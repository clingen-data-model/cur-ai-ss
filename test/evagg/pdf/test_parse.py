from unittest.mock import MagicMock, patch

from lib.agents.table_correction_agent import TableCorrectionResult, correct_tables
from lib.misc.pdf.parse import parse_content
from lib.misc.pdf.paths import (
    apply_table_corrections,
    fulltext_md,
    pdf_extraction_success_path,
    pdf_image_path,
    pdf_json_path,
    pdf_markdown_path,
    pdf_raw_path,
    pdf_section_markdown_path,
    pdf_table_image_path,
    pdf_table_markdown_path,
    pdf_table_vision_markdown_path,
    pdf_tables_dir,
)
from lib.models import PaperDB


async def test_convert_and_extract_creates_outputs(test_file_contents):
    mock_result = MagicMock()
    mock_result.final_output = TableCorrectionResult(
        is_corrupted=False,
    )

    with (
        patch(
            'lib.misc.gcs.upload_and_sign_image',
            return_value='https://example.com/image.png',
        ),
        patch(
            'agents.Runner.run',
            return_value=mock_result,
        ),
    ):
        content = test_file_contents('ACN3-7-1962.pdf', mode='rb')

        paper_db = PaperDB.from_content(content)
        paper_id = paper_db.id
        pdf_raw_path(paper_id).parent.mkdir(parents=True, exist_ok=True)
        pdf_raw_path(paper_id).write_bytes(content)
        await parse_content(paper_id, force=True)

        # ---- core outputs ----
        json_path = pdf_json_path(paper_id)
        md_path = pdf_markdown_path(paper_id)
        success_path = pdf_extraction_success_path(paper_id)

        assert json_path.exists(), 'JSON output was not created'
        assert md_path.exists(), 'Markdown output was not created'
        assert success_path.exists(), 'Success marker file was not created'

        # ---- tables ----
        table_images = []
        table_markdowns = []

        table_id = 0
        while True:
            img = pdf_table_image_path(paper_id, table_id)
            md = pdf_table_markdown_path(paper_id, table_id)

            if not img.exists() and not md.exists():
                break

            if img.exists():
                table_images.append(img)

            if md.exists():
                table_markdowns.append(md)

            table_id += 1

        assert len(table_images) >= 1, 'No table images were extracted'
        assert len(table_markdowns) >= 1, 'No table markdown files were extracted'
        assert len(table_images) == len(table_markdowns), (
            'Table images and table markdown lengths should be equivalent'
        )

        # ---- pictures ----
        images = []
        image_id = 0

        while True:
            img = pdf_image_path(paper_id, image_id)

            if not img.exists():
                break

            images.append(img)
            image_id += 1

        assert len(images) >= 1, 'No pictures were extracted'

        # ---- section markdowns ----
        sections = []
        section_id = 0

        while True:
            section_md = pdf_section_markdown_path(paper_id, section_id)

            if not section_md.exists():
                break

            sections.append(section_md)
            section_id += 1

        assert len(sections) >= 20, 'Not enough sections were extracted'

        with open(pdf_section_markdown_path(paper_id, section_id - 1), 'r') as f:
            assert '## Supporting Information' in f.read()


async def test_correct_tables_leaves_unrecoverable_tables_in_place():
    """A corrupted-but-unrecoverable table must not crash the pipeline."""
    paper_id = 987654
    garbled = '| b | Clin mt1 11l(esladons |\n|---|---|\n| IVI | * ! . - |'

    tables_dir = pdf_tables_dir(paper_id)
    tables_dir.mkdir(parents=True, exist_ok=True)
    pdf_table_markdown_path(paper_id, 0).write_text(garbled)

    raw_md_path = pdf_markdown_path(paper_id)
    raw_md_path.parent.mkdir(parents=True, exist_ok=True)
    raw_md_path.write_text(f'intro\n\n{garbled}\n\noutro')

    mock_result = MagicMock()
    mock_result.final_output = TableCorrectionResult(
        is_corrupted=True,
        corrected_markdown=None,
        conversion_successful=False,
        is_recoverable=False,
    )

    with (
        patch(
            'lib.misc.gcs.upload_and_sign_image',
            return_value='https://example.com/image.png',
        ),
        patch('agents.Runner.run', return_value=mock_result),
    ):
        # Must not raise.
        await correct_tables(paper_id)

    # Original markdown left untouched, no vision file written.
    assert raw_md_path.read_text() == f'intro\n\n{garbled}\n\noutro'
    assert not pdf_table_vision_markdown_path(paper_id, 0).exists()


def _seed_table(paper_id: int, table_id: int, original: str, raw_body: str) -> None:
    pdf_tables_dir(paper_id).mkdir(parents=True, exist_ok=True)
    pdf_table_markdown_path(paper_id, table_id).write_text(original)
    raw_md_path = pdf_markdown_path(paper_id)
    raw_md_path.parent.mkdir(parents=True, exist_ok=True)
    raw_md_path.write_text(raw_body)


def test_apply_table_corrections_prefers_vision_markdown():
    """A .vision.md replaces the corrupted table wherever it appears."""
    paper_id = 987001
    garbled = '| b | Clin mt1 11l(esladons |\n|---|---|\n| IVI | * ! . - |'
    corrected = '| Individual | Age |\n|---|---|\n| HN-F25 | 8 (11) |'

    _seed_table(paper_id, 0, garbled, f'intro\n\n{garbled}\n\noutro')
    pdf_table_vision_markdown_path(paper_id, 0).write_text(corrected)

    assert fulltext_md(paper_id) == f'intro\n\n{corrected}\n\noutro'


def test_apply_table_corrections_noop_without_vision_file():
    """Tables with no vision file are passed through untouched."""
    paper_id = 987002
    garbled = '| b | Clin mt1 |\n|---|---|\n| IVI | * |'

    _seed_table(paper_id, 0, garbled, f'intro\n\n{garbled}\n\noutro')

    assert fulltext_md(paper_id) == f'intro\n\n{garbled}\n\noutro'


def test_apply_table_corrections_is_idempotent():
    """Re-applying against already-corrected markdown changes nothing."""
    paper_id = 987003
    garbled = '| b | Clin mt1 |\n|---|---|\n| IVI | * |'
    corrected = '| Individual | Age |\n|---|---|\n| HN-F25 | 8 (11) |'

    _seed_table(paper_id, 0, garbled, f'intro\n\n{garbled}\n\noutro')
    pdf_table_vision_markdown_path(paper_id, 0).write_text(corrected)

    once = fulltext_md(paper_id)
    assert apply_table_corrections(paper_id, once) == once


async def test_correct_tables_writes_vision_file_without_touching_raw_md():
    """Recovered tables land in .vision.md; raw.md stays raw."""
    paper_id = 987004
    garbled = '| b | Clin mt1 |\n|---|---|\n| IVI | * |'
    corrected = '| Individual | Age |\n|---|---|\n| HN-F25 | 8 (11) |'
    raw_body = f'intro\n\n{garbled}\n\noutro'

    _seed_table(paper_id, 0, garbled, raw_body)

    mock_result = MagicMock()
    mock_result.final_output = TableCorrectionResult(
        is_corrupted=True,
        corrected_markdown=corrected,
        conversion_successful=True,
        is_recoverable=True,
    )

    with (
        patch(
            'lib.misc.gcs.upload_and_sign_image',
            return_value='https://example.com/image.png',
        ),
        patch('agents.Runner.run', return_value=mock_result),
    ):
        await correct_tables(paper_id)

    assert pdf_table_vision_markdown_path(paper_id, 0).read_text() == corrected
    assert pdf_markdown_path(paper_id).read_text() == raw_body
    # ...but readers see the correction.
    assert fulltext_md(paper_id) == f'intro\n\n{corrected}\n\noutro'
