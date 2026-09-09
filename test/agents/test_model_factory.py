import pytest

from lib.agents.model_factory import (
    extraction_model,
    resolve_model,
    split_provider,
    vlm_model,
)
from lib.core.environment import env


def test_openai_prefix_resolves_to_bare_string():
    """The prefix is config-only: the SDK and the OpenAI client both want the
    bare model name."""
    assert resolve_model('openai/gpt-5.6-luna') == 'gpt-5.6-luna'


def test_configured_models_resolve_from_env(monkeypatch):
    monkeypatch.setattr(env, 'EXTRACTION_MODEL', 'openai/gpt-5.6-luna')
    monkeypatch.setattr(env, 'VLM_MODEL', 'openai/gpt-5.6-sol')

    assert extraction_model() == 'gpt-5.6-luna'
    assert vlm_model() == 'gpt-5.6-sol'


@pytest.mark.parametrize('name', ['anthropic/claude-sonnet-5', 'gemini/some-model'])
def test_non_openai_providers_are_rejected_until_routing_lands(name):
    """Raised at agent construction -- process start for the module-level
    agents -- rather than partway through a pipeline run."""
    with pytest.raises(ValueError, match='no route yet'):
        resolve_model(name)


def test_split_provider_returns_both_halves():
    assert split_provider('anthropic/claude-sonnet-5') == (
        'anthropic',
        'claude-sonnet-5',
    )


@pytest.mark.parametrize('name', ['gpt-5.6-luna', 'openai/', '/gpt', ''])
def test_bare_or_malformed_names_rejected(name):
    with pytest.raises(ValueError, match='provider prefix'):
        split_provider(name)
