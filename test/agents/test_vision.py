from types import SimpleNamespace

import pytest

from lib.agents import vision


@pytest.fixture
def completion(monkeypatch):
    """Stub the OpenAI chat completion; records the kwargs it was called with."""
    calls: dict = {}

    def _configure(finish_reason: str | None, content: str | None) -> None:
        def _create(**kwargs):
            calls.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason=finish_reason,
                        message=SimpleNamespace(content=content),
                    )
                ]
            )

        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
        )
        monkeypatch.setattr(vision, 'OpenAI', lambda **_: client)

    return SimpleNamespace(configure=_configure, calls=calls)


def test_returns_content_on_normal_completion(completion):
    completion.configure('stop', '| gene | variant |')

    assert (
        vision.vlm_describe('data:image/png;base64,AAA', 'go') == '| gene | variant |'
    )


def test_discards_truncated_output(completion):
    """A response cut off at the output limit must not pass as a complete
    extraction -- nothing downstream can tell it apart from a whole one."""
    completion.configure('length', '| gene | variant |\n| BRCA1 |')

    assert vision.vlm_describe('data:image/png;base64,AAA', 'go') is None


def test_declines_on_content_filter(completion):
    completion.configure('content_filter', None)

    assert vision.vlm_describe('data:image/png;base64,AAA', 'go') is None


def test_declines_on_any_other_finish_reason(completion):
    completion.configure('tool_calls', 'partial')

    assert vision.vlm_describe('data:image/png;base64,AAA', 'go') is None


def test_treats_missing_finish_reason_as_success(completion):
    completion.configure(None, 'description')

    assert vision.vlm_describe('data:image/png;base64,AAA', 'go') == 'description'


def test_returns_none_for_non_string_content(completion):
    completion.configure('stop', None)

    assert vision.vlm_describe('data:image/png;base64,AAA', 'go') is None


def test_sends_the_image_and_prompt_on_the_configured_model(completion, monkeypatch):
    monkeypatch.setattr(vision.env, 'VLM_MODEL', 'openai/gpt-5.6-sol')
    completion.configure('stop', 'ok')

    vision.vlm_describe('data:image/png;base64,AAA', 'describe it')

    assert completion.calls['model'] == 'gpt-5.6-sol'
    content = completion.calls['messages'][0]['content']
    assert content[0]['image_url']['url'] == 'data:image/png;base64,AAA'
    assert content[1]['text'] == 'describe it'
