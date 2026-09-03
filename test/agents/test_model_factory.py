import pytest
from agents.extensions.models.litellm_model import LitellmModel

from lib.agents.model_factory import provider_api_key, resolve_model, split_provider
from lib.core.environment import env


def test_openai_prefix_resolves_to_bare_string():
    """openai/ stays on the SDK default provider (Responses API) so the
    conversation_id flow keeps working until sessions replace it."""
    assert resolve_model('openai/gpt-5.6-luna') == 'gpt-5.6-luna'


def test_anthropic_prefix_returns_litellm_model(monkeypatch):
    monkeypatch.setattr(env, 'ANTHROPIC_API_KEY', 'sk-ant-test')
    model = resolve_model('anthropic/claude-sonnet-5')
    assert isinstance(model, LitellmModel)
    assert model.model == 'anthropic/claude-sonnet-5'


def test_other_provider_prefix_returns_litellm_model():
    assert isinstance(resolve_model('gemini/some-model'), LitellmModel)


@pytest.mark.parametrize('name', ['gpt-5.6-luna', 'openai/', '/gpt', ''])
def test_bare_or_malformed_names_rejected(name):
    with pytest.raises(ValueError):
        split_provider(name)


def test_provider_api_key(monkeypatch):
    monkeypatch.setattr(env, 'OPENAI_API_KEY', 'sk-openai')
    monkeypatch.setattr(env, 'ANTHROPIC_API_KEY', 'sk-ant')
    assert provider_api_key('openai/gpt-5.6-sol') == 'sk-openai'
    assert provider_api_key('anthropic/claude-fable-5-1') == 'sk-ant'
    assert provider_api_key('gemini/x') is None
