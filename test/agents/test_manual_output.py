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


# --- check hook and run_with_checked_output ----------------------------------


def _reject_gizmo(widget: _Widget) -> None:
    if widget.name == 'gizmo':
        raise ValueError('name: gizmo is not in the paper')


async def test_check_failure_enters_the_repair_loop_with_its_message(monkeypatch):
    responses = iter(
        ['{"name": "gizmo", "count": 3}', '{"name": "widget", "count": 3}']
    )
    prompts = []

    async def fake_run(agent, prompt, **kwargs):
        prompts.append(prompt)
        return _fake_result(next(responses))

    monkeypatch.setattr(manual_output.Runner, 'run', fake_run)

    _, parsed = await manual_output.run_with_manual_output(
        _fake_agent(), 'extract the widget', _Widget, check=_reject_gizmo
    )

    assert parsed == _Widget(name='widget', count=3)
    assert len(prompts) == 2
    assert 'gizmo is not in the paper' in prompts[1]


async def test_check_failing_every_attempt_raises_the_check_error(monkeypatch):
    async def fake_run(agent, prompt, **kwargs):
        return _fake_result('{"name": "gizmo", "count": 3}')

    monkeypatch.setattr(manual_output.Runner, 'run', fake_run)

    with pytest.raises(ValueError, match='gizmo is not in the paper'):
        await manual_output.run_with_manual_output(
            _fake_agent(),
            'extract the widget',
            _Widget,
            check=_reject_gizmo,
            max_attempts=2,
        )


async def test_checked_output_returns_first_result_that_passes(monkeypatch):
    """The native-schema path: the provider validated the shape, only the
    check can fail, and the repair turn quotes it back in the same session."""
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


# --- two-message input (paper block, then task) --------------------------------


async def test_list_input_gets_the_directive_on_the_instructions_item(monkeypatch):
    """The paper item and the data item must reach the provider byte-identical
    (the paper is the prefix every agent shares, the data is what this run
    adds); the directive and schema are constant per agent, so they extend the
    instructions item, which every run of the agent then reads from cache."""
    captured = {}

    async def fake_run(agent, prompt, **kwargs):
        captured['prompt'] = prompt
        return _fake_result('{"name": "gizmo", "count": 3}')

    monkeypatch.setattr(manual_output.Runner, 'run', fake_run)
    paper = {'role': 'user', 'content': 'PAPER AND GENE CONTEXT\n\nthe paper'}
    data = {'role': 'user', 'content': 'Patient JSON:\n{"id": 7}'}

    await manual_output.run_with_manual_output(
        _fake_agent(), [paper, {'role': 'user', 'content': 'rules'}, data], _Widget
    )

    sent = captured['prompt']
    assert sent[0] == paper
    assert sent[2] == data
    assert sent[1]['role'] == 'user'
    assert sent[1]['content'].startswith('rules\n\n')
    assert '"count"' in sent[1]['content']
    assert '"count"' not in sent[0]['content'] + sent[2]['content']


async def test_two_item_input_extends_its_last_item(monkeypatch):
    captured = {}

    async def fake_run(agent, prompt, **kwargs):
        captured['prompt'] = prompt
        return _fake_result('{"name": "gizmo", "count": 3}')

    monkeypatch.setattr(manual_output.Runner, 'run', fake_run)

    await manual_output.run_with_manual_output(
        _fake_agent(),
        [{'role': 'user', 'content': 'paper'}, {'role': 'user', 'content': 'rules'}],
        _Widget,
    )

    sent = captured['prompt']
    assert len(sent) == 2
    assert sent[0]['content'] == 'paper'
    assert (
        sent[1]['content'].startswith('rules\n\n') and '"count"' in sent[1]['content']
    )


async def test_list_input_repair_turn_is_a_plain_string(monkeypatch):
    responses = iter(['nope', '{"name": "gizmo", "count": 3}'])
    prompts = []

    async def fake_run(agent, prompt, **kwargs):
        prompts.append(prompt)
        return _fake_result(next(responses))

    monkeypatch.setattr(manual_output.Runner, 'run', fake_run)

    _, parsed = await manual_output.run_with_manual_output(
        _fake_agent(),
        [{'role': 'user', 'content': 'paper'}, {'role': 'user', 'content': 'rules'}],
        _Widget,
    )

    assert parsed == _Widget(name='gizmo', count=3)
    assert isinstance(prompts[0], list)
    assert isinstance(prompts[1], str) and 'not valid JSON' in prompts[1]


def test_append_to_instructions_rejects_short_lists_and_non_text_items():
    with pytest.raises(ValueError):
        manual_output._append_to_instructions([], 'x')
    with pytest.raises(ValueError):
        manual_output._append_to_instructions([{'role': 'user', 'content': 'p'}], 'x')
    with pytest.raises(TypeError):
        manual_output._append_to_instructions(
            [
                {'role': 'user', 'content': 'paper'},
                {'role': 'user', 'content': [{'type': 'input_text', 'text': 'a'}]},
            ],
            'x',
        )
