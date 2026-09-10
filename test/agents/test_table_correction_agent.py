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
    conversion_successful=False, and the correction record claimed the table
    could not be recovered -- indistinguishable from a genuine dense-symbol
    matrix, and the task still completed.
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
