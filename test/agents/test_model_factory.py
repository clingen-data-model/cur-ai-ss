import pytest
from agents import ModelSettings
from agents.extensions.models.litellm_model import LitellmModel

from lib.agents.model_factory import (
    extraction_model,
    extraction_model_settings,
    model_settings_for,
    provider_api_key,
    resolve_model,
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


def test_openai_gets_empty_model_settings_not_none():
    """Agent.__post_init__ rejects model_settings=None outright (TypeError), so
    the openai/ branch must return an empty ModelSettings(), not None -- the
    'no cache breakpoints' case still has to satisfy the type Agent requires."""
    settings = model_settings_for('openai/gpt-5.6-luna')

    assert settings == ModelSettings()
    assert settings.extra_args is None


def test_anthropic_gets_two_breakpoints_at_the_1h_ttl():
    """system covers instructions+tools (identical every call an agent makes);
    index -1 covers the paper context, targeted by position rather than role
    because a thread with follow-ups has more than one user message and only
    the last is the one being extended. Verified live (2026-09-14, Sonnet 5,
    paper_section_classifier_agent): a forced-cold call wrote
    cache_creation_input_tokens=24201/cache_read_input_tokens=0, and the
    identical prefix resent immediately after read
    cache_read_input_tokens=24201/cache_creation_input_tokens=0 -- a 100% hit,
    not just a non-empty one."""
    settings = model_settings_for('anthropic/claude-sonnet-5')

    points = settings.extra_args['cache_control_injection_points']
    assert points == [
        {
            'location': 'message',
            'role': 'system',
            'control': {'type': 'ephemeral', 'ttl': '1h'},
        },
        {
            'location': 'message',
            'index': -1,
            'control': {'type': 'ephemeral', 'ttl': '1h'},
        },
    ]


def test_settings_stay_under_the_four_breakpoint_cap():
    """MAX_CACHE_CONTROL_BLOCKS = 4 in litellm's
    anthropic_cache_control_hook.py; injection stops silently past the cap
    rather than erroring, so a future third breakpoint added here without
    checking this would degrade instead of failing loudly."""
    settings = model_settings_for('anthropic/claude-sonnet-5')

    assert len(settings.extra_args['cache_control_injection_points']) <= 4


def test_extraction_model_settings_follows_extraction_model(monkeypatch):
    """Same env-driven pattern as extraction_model() itself -- one setting,
    read fresh each call, no separate provider to keep in sync."""
    monkeypatch.setattr(env, 'EXTRACTION_MODEL', 'anthropic/claude-sonnet-5')
    assert extraction_model_settings().extra_args is not None

    monkeypatch.setattr(env, 'EXTRACTION_MODEL', 'openai/gpt-5.6-luna')
    assert extraction_model_settings() == ModelSettings()


def test_split_provider_returns_both_halves():
    assert split_provider('anthropic/claude-sonnet-5') == (
        'anthropic',
        'claude-sonnet-5',
    )


@pytest.mark.parametrize('name', ['gpt-5.6-luna', 'openai/', '/gpt', ''])
def test_bare_or_malformed_names_rejected(name):
    with pytest.raises(ValueError, match='provider prefix'):
        split_provider(name)
