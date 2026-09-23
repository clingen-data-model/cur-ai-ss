"""ask_task_agent resumes the exact agent that ran a task, in its own
session, for a read-only follow-up question -- these confirm the branches
that don't require a real model call: the two "nothing to ask" messages, the
per-task-type agent lookup, and that a resumed run is built the way a
read-only follow-up requires (str output, same session, original tools kept).
"""

from unittest.mock import AsyncMock, patch

import pytest

from lib.core.environment import env
from lib.tasks.agent_session import agent_session
from lib.tasks.handlers import (
    QA_UNSUPPORTED_TASK_TYPES,
    _agent_for_task_type,
    ask_task_agent,
)
from lib.tasks.models import TaskType


@pytest.fixture(autouse=True)
def _isolated_sqlite_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(env, 'CAA_ROOT', str(tmp_path))


async def test_unsupported_task_type_short_circuits_without_touching_session():
    """PDF_PARSING has no agent at all -- confirm this is caught before ever
    looking at agent_session, not just handled downstream."""
    reply = await ask_task_agent(
        task_id=1, task_type=TaskType.PDF_PARSING, paper_id=1, question='why?'
    )

    assert 'no agent conversation' in reply.lower()
    assert await agent_session(1).get_items() == []


async def test_task_never_run_yet_reports_nothing_to_ask_about():
    """HPO_LINKING is supported, but this task id's session is empty --
    nothing was ever run for it, so there is nothing to consult."""
    reply = await ask_task_agent(
        task_id=99, task_type=TaskType.HPO_LINKING, paper_id=1, question='why?'
    )

    assert 'has not been run yet' in reply


async def test_resumes_the_original_agent_read_only_in_its_own_session():
    """The follow-up run must: use the SAME tools as the original agent, force
    output_type=str (the original enforces a structured schema that a prose
    answer wouldn't fit), and resume the exact task's session rather than a
    fresh one."""
    await agent_session(42).add_items(
        [{'role': 'user', 'content': 'original extraction turn'}]
    )
    base_agent = _agent_for_task_type(TaskType.HPO_LINKING, paper_id=1)

    mock_result = AsyncMock()
    mock_result.final_output = 'It matched because the term description overlapped.'
    captured = {}

    async def fake_run(agent, question, *, session, max_turns):
        captured['agent'] = agent
        captured['session'] = session
        captured['question'] = question
        return mock_result

    with patch('lib.tasks.handlers.Runner.run', side_effect=fake_run):
        reply = await ask_task_agent(
            task_id=42,
            task_type=TaskType.HPO_LINKING,
            paper_id=1,
            question='why did this match?',
        )

    assert reply == 'It matched because the term description overlapped.'
    assert captured['question'] == 'why did this match?'
    assert captured['agent'].output_type is str
    assert captured['agent'].tools == base_agent.tools
    assert base_agent.output_type is not str  # clone left the original untouched
    # Same session as the original task, not a fresh one -- proven by history
    # persisting under the same task id after this call.
    assert captured['session'].session_id == agent_session(42).session_id


@pytest.mark.parametrize(
    'task_type', [t for t in TaskType if t not in QA_UNSUPPORTED_TASK_TYPES]
)
async def test_every_supported_task_type_resolves_to_an_agent(task_type):
    assert _agent_for_task_type(task_type, paper_id=1) is not None


@pytest.mark.parametrize('task_type', sorted(QA_UNSUPPORTED_TASK_TYPES, key=str))
async def test_every_unsupported_task_type_resolves_to_none(task_type):
    assert _agent_for_task_type(task_type, paper_id=1) is None
