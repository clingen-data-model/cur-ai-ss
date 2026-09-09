import pytest
from agents.tool_context import ToolContext

from lib.agents import pedigree_describer_agent as pedigree
from lib.agents.pedigree_describer_agent import NOT_A_PEDIGREE


def test_usable_description_is_returned(monkeypatch):
    monkeypatch.setattr(pedigree, 'vlm_describe', lambda *_: 'III-2 affected male')

    assert pedigree._analyze_image_url('data:image/png;base64,AAA') == (
        'III-2 affected male'
    )


def test_no_usable_answer_reads_as_not_a_pedigree(monkeypatch):
    """Truncated and refused answers both land here, so the describer moves to
    the next figure instead of recording half an analysis as authoritative."""
    monkeypatch.setattr(pedigree, 'vlm_describe', lambda *_: None)

    assert pedigree._analyze_image_url('data:image/png;base64,AAA') == NOT_A_PEDIGREE


def test_a_declined_figure_is_never_captured(monkeypatch):
    """NOT_A_PEDIGREE is what keeps PedigreeCapture empty, which is what the
    caller stores as the paper's pedigree analysis."""
    monkeypatch.setattr(pedigree, 'vlm_describe', lambda *_: None)
    capture = pedigree.PedigreeCapture()

    description = pedigree._analyze_image_url('data:image/png;base64,AAA')
    if description.strip() != NOT_A_PEDIGREE:
        capture.record(1, description)

    assert capture.image_id is None
    assert capture.description is None


def _tool_context(tool_name: str) -> ToolContext:
    return ToolContext(
        context=None,
        tool_name=tool_name,
        tool_call_id='call_1',
        tool_arguments='{}',
    )


async def test_provider_failure_fails_the_task_instead_of_answering(monkeypatch):
    """A call that never reached the model is a task failure, not a finding.

    Without failure_error_function=None the SDK converts this into tool output
    ("An error occurred... Please try again"), the agent reports found=False,
    and the worker records a successful task for a paper it never looked at.
    """

    def _raise(*_):
        raise RuntimeError('connection reset')

    monkeypatch.setattr(pedigree, 'vlm_describe', _raise)
    monkeypatch.setattr(
        pedigree, 'image_to_data_url', lambda *_: 'data:image/png;base64,AAA'
    )
    agent, _ = pedigree.pedigree_describer_agent_for_paper(paper_id=1)
    (tool,) = agent.tools

    with pytest.raises(RuntimeError, match='connection reset'):
        await tool.on_invoke_tool(
            _tool_context(tool.name), '{"image_id": 0, "is_supplement": false}'
        )


async def test_a_decline_still_answers_not_a_pedigree(monkeypatch):
    """The other half of the split: what the model said stays a finding."""
    monkeypatch.setattr(pedigree, 'vlm_describe', lambda *_: None)
    monkeypatch.setattr(
        pedigree, 'image_to_data_url', lambda *_: 'data:image/png;base64,AAA'
    )
    agent, capture = pedigree.pedigree_describer_agent_for_paper(paper_id=1)
    (tool,) = agent.tools

    result = await tool.on_invoke_tool(
        _tool_context(tool.name), '{"image_id": 0, "is_supplement": false}'
    )

    assert result == NOT_A_PEDIGREE
    assert capture.image_id is None
