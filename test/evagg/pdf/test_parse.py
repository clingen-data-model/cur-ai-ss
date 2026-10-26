import json
import shutil
from unittest.mock import MagicMock, patch

import pytest
from agents.exceptions import MaxTurnsExceeded

from lib.agents.model_factory import ModelDeclined
from lib.agents.table_correction_agent import (
    JUDGE_MAX_TURNS,
    TableCorrectionResult,
    correct_tables,
)
from lib.misc.pdf.anchors import load_anchors
from lib.misc.pdf.parse import parse_content
from lib.misc.pdf.paths import (
    document_anchored_md_path,
    document_images_dir,
    document_raw_path,
    document_success_path,
    document_table_image_path,
    document_table_markdown_path,
    document_table_unrecovered_path,
    document_table_vision_markdown_path,
    document_tables_dir,
    document_words_json_path,
)
from lib.models import PaperDB


async def test_convert_and_extract_creates_outputs(mocked_root_dir, test_file_contents):
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
        document_raw_path(paper_id).parent.mkdir(parents=True, exist_ok=True)
        document_raw_path(paper_id).write_bytes(content)
        await parse_content(paper_id, force=True)

        assert document_success_path(paper_id).exists()
        assert document_words_json_path(paper_id).exists()
        # Nothing but what the pipeline reads: no Docling dump, no page renders.
        assert sorted(p.name for p in document_raw_path(paper_id).parent.iterdir()) == [
            '_SUCCESS',
            'anchored.md',
            'anchors.json',
            'images',
            'raw.pdf',
            'tables',
            'words.json',
        ]

        anchored = document_anchored_md_path(paper_id).read_text()
        anchors = load_anchors(paper_id)
        assert anchored.count('[paragraph-') >= 100
        assert '## Supporting Information' in anchored  # headers untagged
        table_ids = sorted(a.id for a in anchors if a.id.startswith('table-'))
        figure_ids = sorted(a.id for a in anchors if a.id.startswith('figure-'))
        assert table_ids and figure_ids
        # Files are keyed by the same Docling index as the anchor ids, and
        # every table has its markdown and its image.
        table_stems = sorted(
            p.stem
            for p in document_tables_dir(paper_id).glob('*.md')
            if '.' not in p.stem
        )
        assert [f'table-{s}' for s in table_stems] == table_ids
        assert all(
            document_table_image_path(paper_id, int(s)).exists() for s in table_stems
        )
        assert (
            sorted(
                f'figure-{p.stem}' for p in document_images_dir(paper_id).glob('*.png')
            )
            == figure_ids
        )
        assert all(a.boxes for a in anchors), 'every PDF anchor has a box'


async def test_reparse_drops_the_previous_tables_and_images(
    mocked_root_dir, test_file_contents
):
    """A re-parse starts from empty tables/ and images/: a stale correction
    marker or image under a Docling index the new parse does not use would
    otherwise be read as this parse's."""
    mock_result = MagicMock()
    mock_result.final_output = TableCorrectionResult(is_corrupted=False)
    content = test_file_contents('ACN3-7-1962.pdf', mode='rb')
    paper_id = PaperDB.from_content(content).id
    document_raw_path(paper_id).parent.mkdir(parents=True, exist_ok=True)
    document_raw_path(paper_id).write_bytes(content)
    document_tables_dir(paper_id).mkdir(parents=True)
    document_table_unrecovered_path(paper_id, 99).touch()
    document_images_dir(paper_id).mkdir(parents=True)
    (document_images_dir(paper_id) / '99.png').write_bytes(b'stale')

    with (
        patch(
            'lib.agents.table_correction_agent.image_to_data_url',
            return_value='https://example.com/image.png',
        ),
        patch('agents.Runner.run', return_value=mock_result),
    ):
        await parse_content(paper_id, force=True)

    assert not document_table_unrecovered_path(paper_id, 99).exists()
    assert not (document_images_dir(paper_id) / '99.png').exists()


async def test_correct_tables_leaves_unrecoverable_tables_in_place(mocked_root_dir):
    """A corrupted-but-unrecoverable table must not crash the pipeline."""
    paper_id = 987654
    garbled = '| b | Clin mt1 11l(esladons |\n|---|---|\n| IVI | * ! . - |'

    tables_dir = document_tables_dir(paper_id)
    tables_dir.mkdir(parents=True, exist_ok=True)
    document_table_markdown_path(paper_id, 0).write_text(garbled)

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
    assert document_table_markdown_path(paper_id, 0).read_text() == garbled
    assert not document_table_vision_markdown_path(paper_id, 0).exists()


def _seed_table(paper_id: int, table_id: int, original: str) -> None:
    document_tables_dir(paper_id).mkdir(parents=True, exist_ok=True)
    document_table_markdown_path(paper_id, table_id).write_text(original)


async def test_correct_tables_writes_vision_file_beside_the_original(mocked_root_dir):
    """Recovered tables land in .vision.md; Docling's N.md stays as parsed."""
    paper_id = 987004
    garbled = '| b | Clin mt1 |\n|---|---|\n| IVI | * |'
    corrected = '| Individual | Age |\n|---|---|\n| HN-F25 | 8 (11) |'

    _seed_table(paper_id, 0, garbled)

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

    assert document_table_vision_markdown_path(paper_id, 0).read_text() == corrected
    assert document_table_markdown_path(paper_id, 0).read_text() == garbled


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


async def test_unrecovered_marker_written_when_unrecoverable(mocked_root_dir):
    """The give-up path leaves a marker file, not just a log line."""
    paper_id = 987020
    garbled = '| b | Clin mt1 |\n|---|---|\n| IVI | * |'
    _seed_table(paper_id, 0, garbled)

    await _run_correct_tables(
        paper_id,
        TableCorrectionResult(
            is_corrupted=True,
            corrected_markdown=None,
            conversion_successful=False,
            is_recoverable=False,
        ),
    )

    assert document_table_unrecovered_path(paper_id, 0).exists()
    assert not document_table_vision_markdown_path(paper_id, 0).exists()


async def test_an_accepted_extraction_that_is_not_a_table_is_marked_unrecovered(
    mocked_root_dir,
):
    """The judge's acceptance is checked in code: prose, or a ragged grid, is
    never written as a correction however the verdict reads."""
    paper_id = 987022
    garbled = '| b | Clin mt1 |\n|---|---|\n| IVI | * |'
    _seed_table(paper_id, 0, garbled)

    await _run_correct_tables(
        paper_id,
        TableCorrectionResult(
            is_corrupted=True,
            corrected_markdown='I could not read this table from the image.',
            conversion_successful=True,
            is_recoverable=True,
        ),
    )

    assert document_table_unrecovered_path(paper_id, 0).exists()
    assert not document_table_vision_markdown_path(paper_id, 0).exists()


async def test_recovered_table_clears_a_stale_unrecovered_marker(mocked_root_dir):
    paper_id = 987021
    garbled = '| b | Clin mt1 |\n|---|---|\n| IVI | * |'
    corrected = '| Individual | Age |\n|---|---|\n| HN-F25 | 8 (11) |'
    _seed_table(paper_id, 0, garbled)
    document_table_unrecovered_path(paper_id, 0).touch()  # from an earlier run

    await _run_correct_tables(
        paper_id,
        TableCorrectionResult(
            is_corrupted=True,
            corrected_markdown=corrected,
            conversion_successful=True,
            is_recoverable=True,
        ),
    )

    assert not document_table_unrecovered_path(paper_id, 0).exists()


@pytest.mark.parametrize(
    'no_verdict',
    [
        MaxTurnsExceeded('Max turns (4) exceeded'),
        ModelDeclined('anthropic/claude-fable-5-1', 'content_filter'),
    ],
    ids=['max_turns', 'declined'],
)
async def test_a_judge_with_no_verdict_marks_the_table_unrecovered(
    mocked_root_dir, no_verdict
):
    """A safety-classifier refusal of the judge call (paper 106, table 2) used
    to propagate as MaxTurnsExceeded and fail the whole PDF parse. Either way
    the judge ends without a verdict, the table is left as parsed, marked, and
    the next table is still checked."""
    paper_id = 987023
    garbled = '| Mock ND |\n|---|\n| Wild-type 146.7 |'
    clean = '| Individual | Age |\n|---|---|\n| HN-F25 | 8 (11) |'
    _seed_table(paper_id, 0, garbled)
    document_table_markdown_path(paper_id, 1).write_text(clean)
    document_table_unrecovered_path(paper_id, 1).touch()  # from an earlier run

    ok = MagicMock()
    ok.final_output = TableCorrectionResult(is_corrupted=False)
    with (
        patch(
            'lib.agents.table_correction_agent.image_to_data_url',
            return_value='https://example.com/image.png',
        ),
        patch('agents.Runner.run', side_effect=[no_verdict, ok]) as run,
    ):
        await correct_tables(paper_id)  # must not raise

    assert document_table_unrecovered_path(paper_id, 0).exists()
    assert not document_table_vision_markdown_path(paper_id, 0).exists()
    assert document_table_markdown_path(paper_id, 0).read_text() == garbled
    # The second table got its own run and its stale marker cleared.
    assert not document_table_unrecovered_path(paper_id, 1).exists()
    assert run.call_count == 2
    # Bounded: a refusal is one billed request per turn, not the SDK's ten.
    assert all(
        call.kwargs['max_turns'] == JUDGE_MAX_TURNS for call in run.call_args_list
    )


async def test_clean_table_leaves_no_marker(mocked_root_dir):
    paper_id = 987022
    table = '| Individual | Age |\n|---|---|\n| HN-F25 | 8 (11) |'
    _seed_table(paper_id, 0, table)
    document_table_unrecovered_path(paper_id, 0).touch()  # from an earlier run

    await _run_correct_tables(paper_id, TableCorrectionResult(is_corrupted=False))

    assert not document_table_unrecovered_path(paper_id, 0).exists()
    assert not document_table_vision_markdown_path(paper_id, 0).exists()
