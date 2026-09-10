import pytest

from lib.agents.model_factory import extraction_model, resolve_model, vlm_model
from lib.core.environment import env
from lib.core.model_names import ROUTABLE_PROVIDERS, split_provider


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
    """A backstop only -- the settings validator rejects these at load, which is
    what keeps the error out of a function_tool body."""
    with pytest.raises(ValueError, match='no route yet'):
        resolve_model(name)


def test_every_routable_provider_resolves():
    """Guards the invariant the settings validator relies on: anything it lets
    through, this module can resolve. Widening ROUTABLE_PROVIDERS without adding
    a branch to resolve_model fails here."""
    for provider in ROUTABLE_PROVIDERS:
        assert resolve_model(f'{provider}/some-model') == 'some-model'


def test_split_provider_returns_both_halves():
    assert split_provider('anthropic/claude-sonnet-5') == (
        'anthropic',
        'claude-sonnet-5',
    )


@pytest.mark.parametrize('name', ['gpt-5.6-luna', 'openai/', '/gpt', ''])
def test_bare_or_malformed_names_rejected(name):
    with pytest.raises(ValueError, match='provider prefix'):
        split_provider(name)
