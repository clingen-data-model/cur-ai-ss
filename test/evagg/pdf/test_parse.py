import json
import shutil
from unittest.mock import MagicMock, patch

from lib.agents.table_correction_agent import TableCorrectionResult, correct_tables
from lib.bin.backfill_documents import backfill_paper
from lib.misc.pdf.anchors import load_anchors
from lib.misc.pdf.parse import parse_content
from lib.misc.pdf.paths import (
    document_anchored_md_path,
    document_dir,
    document_images_dir,
    document_success_path,
    document_tables_dir,
    pdf_extraction_success_path,
    pdf_image_path,
    pdf_json_path,
    pdf_markdown_path,
    pdf_raw_path,
    pdf_table_image_path,
    pdf_table_markdown_path,
    pdf_table_unrecovered_path,
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
            'lib.agents.table_correction_agent.image_to_data_url',
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

        # ---- anchor-indexed document, written side by side ----
        assert document_success_path(paper_id).exists()
        anchored = document_anchored_md_path(paper_id).read_text()
        anchors = load_anchors(paper_id)
        assert anchored.count('[paragraph-') >= 100
        assert '## Supporting Information' in anchored  # headers untagged
        table_ids = sorted(a.id for a in anchors if a.id.startswith('table-'))
        figure_ids = sorted(a.id for a in anchors if a.id.startswith('figure-'))
        assert table_ids and figure_ids
        # Files are keyed by the same Docling index as the anchor ids.
        assert (
            sorted(
                f'table-{p.stem}'
                for p in document_tables_dir(paper_id).glob('*.md')
                if '.' not in p.stem
            )
            == table_ids
        )
        assert (
            sorted(
                f'figure-{p.stem}' for p in document_images_dir(paper_id).glob('*.png')
            )
            == figure_ids
        )
        assert all(a.boxes for a in anchors), 'every PDF anchor has a box'

        # The backfill (from raw.json) must produce exactly what the live parse did.
        live_md, live_anchors = anchored, anchors
        shutil.rmtree(document_dir(paper_id))
        backfill_paper(paper_id)
        assert document_anchored_md_path(paper_id).read_text() == live_md
        assert load_anchors(paper_id) == live_anchors


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
            'lib.agents.table_correction_agent.image_to_data_url',
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
            'lib.agents.table_correction_agent.image_to_data_url',
            return_value='https://example.com/image.png',
        ),
        patch('agents.Runner.run', return_value=mock_result),
    ):
        await correct_tables(paper_id)

    assert pdf_table_vision_markdown_path(paper_id, 0).read_text() == corrected
    assert pdf_markdown_path(paper_id).read_text() == raw_body


async def _run_correct_tables(paper_id: int, result: TableCorrectionResult) -> None:
    mock_result = MagicMock()
    mock_result.final_output = result
    with (
        patch(
            'lib.agents.table_correction_agent.image_to_data_url',
            return_value='https://example.com/image.png',
        ),
        patch('agents.Runner.run', return_value=mock_result),
    ):
        await correct_tables(paper_id)


async def test_unrecovered_marker_written_when_unrecoverable():
    """The give-up path leaves a marker file, not just a log line."""
    paper_id = 987020
    garbled = '| b | Clin mt1 |\n|---|---|\n| IVI | * |'
    _seed_table(paper_id, 0, garbled, f'intro\n\n{garbled}\n\noutro')

    await _run_correct_tables(
        paper_id,
        TableCorrectionResult(
            is_corrupted=True,
            corrected_markdown=None,
            conversion_successful=False,
            is_recoverable=False,
        ),
    )

    assert pdf_table_unrecovered_path(paper_id, 0).exists()
    assert not pdf_table_vision_markdown_path(paper_id, 0).exists()


async def test_recovered_table_clears_a_stale_unrecovered_marker():
    paper_id = 987021
    garbled = '| b | Clin mt1 |\n|---|---|\n| IVI | * |'
    corrected = '| Individual | Age |\n|---|---|\n| HN-F25 | 8 (11) |'
    _seed_table(paper_id, 0, garbled, f'intro\n\n{garbled}\n\noutro')
    pdf_table_unrecovered_path(paper_id, 0).touch()  # from an earlier run

    await _run_correct_tables(
        paper_id,
        TableCorrectionResult(
            is_corrupted=True,
            corrected_markdown=corrected,
            conversion_successful=True,
            is_recoverable=True,
        ),
    )

    assert not pdf_table_unrecovered_path(paper_id, 0).exists()


async def test_clean_table_leaves_no_marker():
    paper_id = 987022
    table = '| Individual | Age |\n|---|---|\n| HN-F25 | 8 (11) |'
    _seed_table(paper_id, 0, table, f'intro\n\n{table}\n\noutro')
    pdf_table_unrecovered_path(paper_id, 0).touch()  # from an earlier run

    await _run_correct_tables(paper_id, TableCorrectionResult(is_corrupted=False))

    assert not pdf_table_unrecovered_path(paper_id, 0).exists()
    assert not pdf_table_vision_markdown_path(paper_id, 0).exists()
