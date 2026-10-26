from pathlib import Path

import pytest
from agents.tool_context import ToolContext

from lib.agents import table_correction_agent as tca


def _tool_context(tool_name: str) -> ToolContext:
    return ToolContext(
        context=None,
        tool_name=tool_name,
        tool_call_id='call_1',
        tool_arguments='{}',
    )


def _tool(monkeypatch, vlm_describe):
    monkeypatch.setattr(tca, 'vlm_describe', vlm_describe)
    monkeypatch.setattr(
        tca, 'image_to_data_url', lambda *_: 'data:image/png;base64,AAA'
    )
    agent = tca.table_correction_agent_for_image(Path('table.png'))
    (tool,) = agent.tools
    return tool


async def test_extracted_markdown_is_returned(monkeypatch):
    tool = _tool(monkeypatch, lambda *_: '| gene |\n| --- |\n| BRCA1 |')

    result = await tool.on_invoke_tool(_tool_context('x'), '{}')

    assert result == '| gene |\n| --- |\n| BRCA1 |'


async def test_provider_failure_fails_the_task_instead_of_answering(monkeypatch):
    """A call that never reached the model must not be recorded as a judgement
    about the table.

    Under the SDK's default handler this became tool output, the agent set
    conversion_successful=False, and the table was marked unrecovered --
    indistinguishable from a genuine dense-symbol matrix, and the task still
    completed.
    """

    def _raise(*_):
        raise RuntimeError('connection reset')

    tool = _tool(monkeypatch, _raise)

    with pytest.raises(RuntimeError, match='connection reset'):
        await tool.on_invoke_tool(_tool_context('x'), '{}')


async def test_a_decline_still_answers_empty(monkeypatch):
    """The other half of the split: a truncated or refused answer stays a
    finding, so a genuinely unreadable table is still an acceptable outcome."""
    tool = _tool(monkeypatch, lambda *_: None)

    assert await tool.on_invoke_tool(_tool_context('x'), '{}') == ''


def test_the_agent_runs_on_the_vision_model_not_the_extraction_model(monkeypatch):
    monkeypatch.setattr(tca.env, 'EXTRACTION_MODEL', 'openai/extraction-model')
    monkeypatch.setattr(tca.env, 'VLM_MODEL', 'openai/vision-model')

    agent = tca.table_correction_agent_for_image(Path('table.png'))

    assert agent.model == 'vision-model'


@pytest.mark.parametrize(
    'markdown',
    [
        '| gene | status |\n| --- | --- |\n| BRCA1 | + |',
        '| gene | status |\n|:---|---:|\n| BRCA1 | + |\n| BRCA2 | - |',
        'gene | status\n--- | ---\nBRCA1 | +',  # pipes at the edges are optional
        # A dense symbol grid is a table like any other.
        '| Variant | A | B | C |\n|---|---|---|---|\n| p.X | + | - | na |\n| p.Y | U | + | - |',
    ],
)
def test_a_well_formed_table_is_a_header_a_separator_and_uniform_rows(markdown):
    assert tca.is_well_formed_table(markdown)


@pytest.mark.parametrize(
    'markdown',
    [
        '',
        'The table could not be read reliably from the image.',
        '| gene |\n| --- |',  # no data row
        '| gene | status |\n| --- | --- |\n| BRCA1 |',  # ragged
        '| gene | status |\n| BRCA1 | + |\n| BRCA2 | - |',  # no separator
    ],
)
def test_anything_else_is_not_a_well_formed_table(markdown):
    assert not tca.is_well_formed_table(markdown)


def test_the_judge_rejects_on_structure_not_on_what_the_table_is_a_grid_of():
    """Paper 125 table 1 (2026-10-26): a 26-by-16 grid of +/- symbols came back
    from the vision read complete and well-formed, and the judge threw it away
    in three runs of four because its instructions named 'dense matrices of
    tiny symbols' as the example of an unrecoverable table. It cannot see the
    image, so structure is the only test it can apply."""
    text = ' '.join(tca.TABLE_CORRECTION_INSTRUCTIONS.split())
    assert 'dense matrices' not in text
    assert 'well-formed' in text
    assert 'not a reason to reject' in text
