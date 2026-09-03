from agents.extensions.models.litellm_model import LitellmModel

from lib.agents.model_factory import resolve_model
from lib.core.environment import env


def test_bare_name_returns_plain_string():
    """No provider prefix -> agents SDK default OpenAI provider."""
    assert resolve_model('gpt-5.6-luna') == 'gpt-5.6-luna'


def test_anthropic_prefix_returns_litellm_model(monkeypatch):
    monkeypatch.setattr(env, 'ANTHROPIC_API_KEY', 'sk-ant-test')
    model = resolve_model('anthropic/claude-sonnet-5')
    assert isinstance(model, LitellmModel)
    assert model.model == 'anthropic/claude-sonnet-5'


def test_other_provider_prefix_returns_litellm_model():
    model = resolve_model('gemini/some-model')
    assert isinstance(model, LitellmModel)
