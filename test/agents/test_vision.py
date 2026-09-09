from types import SimpleNamespace

import pytest

from lib.agents import vision


@pytest.fixture
def completion(monkeypatch):
    """Stub litellm.completion; returns the kwargs it was called with."""
    calls: dict = {}

    def _stub(finish_reason: str | None, content: str | None) -> None:
        def _completion(**kwargs):
            calls.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason=finish_reason,
                        message=SimpleNamespace(content=content),
                    )
                ]
            )

        monkeypatch.setattr(vision.litellm, 'completion', _completion)

    return SimpleNamespace(configure=_stub, calls=calls)


def test_returns_content_on_normal_completion(completion):
    completion.configure('stop', '| gene | variant |')

    assert (
        vision.vlm_describe('data:image/png;base64,AAA', 'go') == '| gene | variant |'
    )


def test_discards_truncated_output(completion):
    """A response cut off at max_tokens must not pass as a complete extraction."""
    completion.configure('length', '| gene | variant |\n| BRCA1 |')

    assert vision.vlm_describe('data:image/png;base64,AAA', 'go') is None


def test_declines_on_refusal(completion):
    """LiteLLM maps an Anthropic refusal stop reason to 'content_filter'."""
    completion.configure('content_filter', None)

    assert vision.vlm_describe('data:image/png;base64,AAA', 'go') is None


def test_treats_missing_finish_reason_as_success(completion):
    completion.configure(None, 'description')

    assert vision.vlm_describe('data:image/png;base64,AAA', 'go') == 'description'


def test_returns_none_for_non_string_content(completion):
    completion.configure('stop', None)

    assert vision.vlm_describe('data:image/png;base64,AAA', 'go') is None


def test_bounds_max_tokens_and_sends_the_image(completion):
    completion.configure('stop', 'ok')

    vision.vlm_describe('data:image/png;base64,AAA', 'describe it')

    assert completion.calls['max_tokens'] == vision.VLM_MAX_TOKENS
    content = completion.calls['messages'][0]['content']
    assert content[0]['image_url']['url'] == 'data:image/png;base64,AAA'
    assert content[1]['text'] == 'describe it'
