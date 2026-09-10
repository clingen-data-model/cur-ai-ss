import pytest
from agents.extensions.models.litellm_model import LitellmModel

from lib.agents.model_factory import (
    extraction_model,
    provider_api_key,
    resolve_model,
    responses_api_model,
    vlm_model,
)
from lib.core.environment import env
from lib.core.model_names import (
    PROVIDER_KEY_SETTINGS,
    ROUTABLE_PROVIDERS,
    split_provider,
)


def test_openai_prefix_resolves_to_bare_string():
    """The prefix is config-only: the agents SDK's default provider wants the
    bare model name."""
    assert resolve_model('openai/gpt-5.6-luna') == 'gpt-5.6-luna'


def test_anthropic_routes_through_litellm_with_the_full_name():
    """LiteLLM routes on the prefix, so the name must reach it whole -- a bare
    'claude-sonnet-5' would leave the provider to be guessed."""
    model = resolve_model('anthropic/claude-sonnet-5')

    assert isinstance(model, LitellmModel)
    assert model.model == 'anthropic/claude-sonnet-5'


def test_anthropic_carries_the_configured_key(monkeypatch):
    """The key comes from Env rather than litellm's ambient lookup, so one
    source of truth decides which credentials a run uses."""
    monkeypatch.setattr(env, 'ANTHROPIC_API_KEY', 'sk-ant-configured')

    model = resolve_model('anthropic/claude-sonnet-5')

    assert isinstance(model, LitellmModel)
    assert model.api_key == 'sk-ant-configured'


def test_configured_models_resolve_from_env(monkeypatch):
    monkeypatch.setattr(env, 'EXTRACTION_MODEL', 'openai/gpt-5.6-luna')
    monkeypatch.setattr(env, 'VLM_MODEL', 'openai/gpt-5.6-sol')

    assert extraction_model() == 'gpt-5.6-luna'


def test_vlm_model_keeps_its_prefix(monkeypatch):
    """Unlike the agents, the vision tools hand the name to litellm directly,
    which needs the prefix to pick a provider."""
    monkeypatch.setattr(env, 'VLM_MODEL', 'openai/gpt-5.6-sol')

    assert vlm_model() == 'openai/gpt-5.6-sol'


@pytest.mark.parametrize('name', ['gemini/some-model', 'opanai/gpt-5.6-luna'])
def test_unroutable_providers_are_rejected(name):
    """A backstop only -- the settings validator rejects these at load, which is
    what keeps the error out of a function_tool body."""
    with pytest.raises(ValueError, match='no route yet'):
        resolve_model(name)


def test_every_routable_provider_resolves():
    """Guards the invariant the settings validator relies on: anything it lets
    through, this module can resolve. Widening ROUTABLE_PROVIDERS without adding
    a branch to resolve_model fails here."""
    for provider in ROUTABLE_PROVIDERS:
        assert resolve_model(f'{provider}/some-model') is not None


def test_every_routable_provider_has_a_key_setting():
    """The other half of that invariant: validate_models indexes this map
    directly, so a provider missing from it is a KeyError at settings load."""
    for provider in ROUTABLE_PROVIDERS:
        assert provider in PROVIDER_KEY_SETTINGS
        assert hasattr(env, PROVIDER_KEY_SETTINGS[provider])


def test_provider_api_key_follows_the_provider(monkeypatch):
    monkeypatch.setattr(env, 'OPENAI_API_KEY', 'sk-openai')
    monkeypatch.setattr(env, 'ANTHROPIC_API_KEY', 'sk-ant')

    assert provider_api_key('openai/gpt-5.6-luna') == 'sk-openai'
    assert provider_api_key('anthropic/claude-sonnet-5') == 'sk-ant'


def test_responses_api_model_returns_the_bare_openai_name(monkeypatch):
    monkeypatch.setattr(env, 'EXTRACTION_MODEL', 'openai/gpt-5.6-luna')

    assert responses_api_model() == 'gpt-5.6-luna'


def test_responses_api_model_refuses_a_non_openai_model(monkeypatch):
    """This path needs OpenAI's server-side conversation state. Resolving it
    anyway would hand a LitellmModel to the OpenAI client, or send a Claude
    model name to OpenAI -- both fail confusingly at request time instead."""
    monkeypatch.setattr(env, 'EXTRACTION_MODEL', 'anthropic/claude-sonnet-5')

    with pytest.raises(ValueError, match='sessions refactor'):
        responses_api_model()


def test_split_provider_returns_both_halves():
    assert split_provider('anthropic/claude-sonnet-5') == (
        'anthropic',
        'claude-sonnet-5',
    )


@pytest.mark.parametrize('name', ['gpt-5.6-luna', 'openai/', '/gpt', ''])
def test_bare_or_malformed_names_rejected(name):
    with pytest.raises(ValueError, match='provider prefix'):
        split_provider(name)
