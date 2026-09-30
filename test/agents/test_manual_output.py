"""run_with_checked_output: the provider validates the shape, so only the
cross-document check (citations naming real blocks) can fail, and the repair
turn quotes it back in the same session. See lib/agents/manual_output.py.
"""

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from lib.agents import manual_output


class _Widget(BaseModel):
    name: str
    count: int


def _fake_agent() -> Any:
    return SimpleNamespace(name='widget_extractor')


def _reject_gizmo(widget: _Widget) -> None:
    if widget.name == 'gizmo':
        raise ValueError('name: gizmo is not in the paper')


async def test_checked_output_returns_first_result_that_passes(monkeypatch):
    responses = iter([_Widget(name='gizmo', count=1), _Widget(name='widget', count=1)])
    calls = []

    async def fake_run(agent, prompt, **kwargs):
        calls.append((prompt, kwargs.get('session')))
        return SimpleNamespace(final_output=next(responses))

    monkeypatch.setattr(manual_output.Runner, 'run', fake_run)
    session = object()

    result = await manual_output.run_with_checked_output(
        _fake_agent(), 'extract the widget', _reject_gizmo, session=session
    )

    assert result.final_output == _Widget(name='widget', count=1)
    assert calls[0] == ('extract the widget', session)
    assert 'gizmo is not in the paper' in calls[1][0]
    assert calls[1][1] is session


async def test_checked_output_passing_first_time_runs_once(monkeypatch):
    calls = []

    async def fake_run(agent, prompt, **kwargs):
        calls.append(prompt)
        return SimpleNamespace(final_output=_Widget(name='widget', count=1))

    monkeypatch.setattr(manual_output.Runner, 'run', fake_run)

    await manual_output.run_with_checked_output(
        _fake_agent(), 'extract the widget', _reject_gizmo
    )

    assert calls == ['extract the widget']


async def test_checked_output_exhausting_attempts_raises(monkeypatch):
    async def fake_run(agent, prompt, **kwargs):
        return SimpleNamespace(final_output=_Widget(name='gizmo', count=1))

    monkeypatch.setattr(manual_output.Runner, 'run', fake_run)

    with pytest.raises(ValueError, match='gizmo is not in the paper'):
        await manual_output.run_with_checked_output(
            _fake_agent(), 'extract the widget', _reject_gizmo, max_attempts=2
        )


async def test_list_input_is_passed_through_and_the_repair_turn_is_a_string(
    monkeypatch,
):
    """The paper, instructions and data items must reach the provider exactly
    as `lib.tasks.handlers.paper_input` built them (each is a prompt-cache
    prefix); a repair turn is a plain string appended to the same session."""
    responses = iter([_Widget(name='gizmo', count=1), _Widget(name='widget', count=1)])
    prompts = []

    async def fake_run(agent, prompt, **kwargs):
        prompts.append(prompt)
        return SimpleNamespace(final_output=next(responses))

    monkeypatch.setattr(manual_output.Runner, 'run', fake_run)
    items = [
        {'role': 'user', 'content': 'paper'},
        {'role': 'user', 'content': 'rules'},
        {'role': 'user', 'content': 'data'},
    ]

    await manual_output.run_with_checked_output(
        _fake_agent(), list(items), _reject_gizmo
    )

    assert prompts[0] == items
    assert isinstance(prompts[1], str)
