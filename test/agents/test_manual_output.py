"""run_with_manual_output backs the agents whose schema is too complex for
provider-side structured output enforcement (see lib/agents/manual_output.py's
module docstring) -- these confirm it actually validates and repairs client-side
rather than trusting a provider schema that was never sent.
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


def _fake_result(text: str) -> Any:
    return SimpleNamespace(final_output=text)


async def test_valid_json_on_first_attempt_needs_no_repair(monkeypatch):
    calls = []

    async def fake_run(agent, prompt, **kwargs):
        calls.append(prompt)
        return _fake_result('{"name": "gizmo", "count": 3}')

    monkeypatch.setattr(manual_output.Runner, 'run', fake_run)

    result, parsed = await manual_output.run_with_manual_output(
        _fake_agent(), 'extract the widget', _Widget
    )

    assert parsed == _Widget(name='gizmo', count=3)
    assert result.final_output == '{"name": "gizmo", "count": 3}'
    assert len(calls) == 1


async def test_code_fenced_json_is_accepted():
    fenced = '```json\n{"name": "gizmo", "count": 3}\n```'
    assert manual_output._strip_code_fence(fenced) == '{"name": "gizmo", "count": 3}'


async def test_invalid_json_is_repaired_on_a_later_attempt(monkeypatch):
    responses = iter(
        [
            'not json at all',
            '{"name": "gizmo", "count": 3}',
        ]
    )
    prompts = []

    async def fake_run(agent, prompt, **kwargs):
        prompts.append(prompt)
        return _fake_result(next(responses))

    monkeypatch.setattr(manual_output.Runner, 'run', fake_run)

    result, parsed = await manual_output.run_with_manual_output(
        _fake_agent(), 'extract the widget', _Widget, max_attempts=3
    )

    assert parsed == _Widget(name='gizmo', count=3)
    assert len(prompts) == 2
    # The repair turn describes the failure rather than resending the schema.
    assert 'not valid JSON' in prompts[1]


async def test_exhausting_every_attempt_raises(monkeypatch):
    async def fake_run(agent, prompt, **kwargs):
        return _fake_result('still not json')

    monkeypatch.setattr(manual_output.Runner, 'run', fake_run)

    with pytest.raises(Exception):
        await manual_output.run_with_manual_output(
            _fake_agent(), 'extract the widget', _Widget, max_attempts=2
        )


async def test_initial_prompt_embeds_the_json_schema(monkeypatch):
    captured = {}

    async def fake_run(agent, prompt, **kwargs):
        captured['prompt'] = prompt
        return _fake_result('{"name": "gizmo", "count": 3}')

    monkeypatch.setattr(manual_output.Runner, 'run', fake_run)

    await manual_output.run_with_manual_output(
        _fake_agent(), 'extract the widget', _Widget
    )

    assert 'extract the widget' in captured['prompt']
    assert '"count"' in captured['prompt']
    assert 'no markdown code' in captured['prompt']


async def test_runner_kwargs_are_forwarded_to_every_attempt(monkeypatch):
    seen_sessions = []

    async def fake_run(agent, prompt, **kwargs):
        seen_sessions.append(kwargs.get('session'))
        if len(seen_sessions) == 1:
            return _fake_result('not json')
        return _fake_result('{"name": "gizmo", "count": 3}')

    monkeypatch.setattr(manual_output.Runner, 'run', fake_run)
    sentinel_session = object()

    await manual_output.run_with_manual_output(
        _fake_agent(),
        'extract the widget',
        _Widget,
        session=sentinel_session,
    )

    assert seen_sessions == [sentinel_session, sentinel_session]
