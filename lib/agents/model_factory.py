"""Resolve configured model names into values the agents SDK can consume.

Every configured model name carries a LiteLLM-style provider prefix
('openai/gpt-5.6-luna', 'anthropic/claude-sonnet-5'); bare names are rejected so
the provider is always explicit in config.

'openai/' resolves to the plain model string, which the agents SDK's default
provider (the Responses API) takes as-is. That is deliberate rather than
incidental: the pipeline still relies on the Responses API's server-side
conversation_id for additional-context reruns, and LitellmModel ignores that
parameter -- it is annotated `# unused` at litellm_model.py:161 and :271 in the
locked 0.7.0, so routing OpenAI through LiteLLM would silently drop the
conversation history rather than fail. Once client-side sessions replace
conversation_id, this special case can go.

Any other provider routes through LitellmModel. The settings validator rejects
an unroutable provider at load, so by the time anything here runs the provider
is routable; the raise below is a backstop for that invariant, not the primary
guard. It must not become the thing that catches an unroutable name, because
both vision tools call into this from inside a function_tool body, where the
SDK's default error handler would turn the exception into text for the model
rather than failing the run.
"""

from agents import ModelSettings
from agents.extensions.models.litellm_model import LitellmModel
from agents.models.interface import Model

from lib.core.environment import env
from lib.core.model_names import (
    PROVIDER_KEY_SETTINGS,
    ROUTABLE_PROVIDERS,
    split_provider,
)

# TTL is the ceiling Anthropic offers -- '5m' or '1h', no longer option -- and is
# measured from the start of the request that writes *or reads* the entry, so a
# hit refreshes it. '1h' covers the ~40 runs/paper gap that '5m' would mostly
# miss, at the cost of a 2x (not 1.25x) write; see docs/anthropic-migration.md
# for the break-even math.
_CACHE_CONTROL = {'type': 'ephemeral', 'ttl': '1h'}


def extraction_model() -> Model | str:
    """The model every text-extraction agent runs on."""
    return resolve_model(env.EXTRACTION_MODEL)


def extraction_model_settings() -> ModelSettings:
    """Model settings every text-extraction agent runs with."""
    return model_settings_for(env.EXTRACTION_MODEL)


def model_settings_for(name: str) -> ModelSettings:
    """Prompt-cache breakpoints for a configured model, gated on provider.

    Anthropic only: ModelSettings.extra_args is splatted as top-level kwargs
    into whichever API the model resolves to, including the OpenAI Responses
    call the agents SDK's default provider makes. Sending
    cache_control_injection_points there is not a no-op -- OpenAI does not know
    the parameter, so an openai/ model gets the empty ModelSettings() the type
    requires (Agent.__post_init__ rejects None) rather than these breakpoints.

    Two breakpoints, not one: 'system' covers the instructions and tool
    definitions, which are identical on every call an agent makes; index -1
    covers the paper context in the last user message, which is what makes a
    tool loop's later turns and a same-session follow-up read instead of
    resend. Role targeting stamps every message of that role, so 'system' is
    safe (agents send exactly one), but the paper must be targeted by position
    -- a thread that has accumulated follow-ups would otherwise stamp the first
    four user messages and miss the one actually being extended.
    """
    provider, _ = split_provider(name)
    if provider != 'anthropic':
        return ModelSettings()
    return ModelSettings(
        extra_args={
            'cache_control_injection_points': [
                {'location': 'message', 'role': 'system', 'control': _CACHE_CONTROL},
                {'location': 'message', 'index': -1, 'control': _CACHE_CONTROL},
            ]
        }
    )


def vlm_model() -> str:
    """The model the vision tools run on, as a LiteLLM-routable name.

    Unlike the agents, the vision tools call litellm.completion directly rather
    than going through the SDK, and litellm routes on the prefix itself -- so
    this hands back the configured name whole, including 'openai/'.
    """
    split_provider(env.VLM_MODEL)  # reject a bare name here too
    return env.VLM_MODEL


def resolve_model(name: str) -> Model | str:
    provider, bare = split_provider(name)
    if provider == 'openai':
        return bare
    if provider in ROUTABLE_PROVIDERS:
        return LitellmModel(name, api_key=provider_api_key(name))
    raise ValueError(
        f'Model {name!r} names provider {provider!r}, which has no route yet. '
        f'Supported: {", ".join(sorted(ROUTABLE_PROVIDERS))}.'
    )


def provider_api_key(name: str) -> str | None:
    """The configured API key for the provider a model name belongs to."""
    provider, _ = split_provider(name)
    setting = PROVIDER_KEY_SETTINGS.get(provider)
    return getattr(env, setting) if setting else None
