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

from agents.extensions.models.litellm_model import LitellmModel
from agents.models.interface import Model

from lib.core.environment import env
from lib.core.model_names import (
    PROVIDER_KEY_SETTINGS,
    ROUTABLE_PROVIDERS,
    split_provider,
)


def extraction_model() -> Model | str:
    """The model every text-extraction agent runs on."""
    return resolve_model(env.EXTRACTION_MODEL)


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


def responses_api_model() -> str:
    """The bare model name for a direct OpenAI Responses API call.

    Two call sites still talk to the Responses API without going through the
    agents SDK, because they depend on server-side conversation state that only
    OpenAI has: the chat follow-up turn in lib/api/app.py and
    ensure_conversation_id in lib/tasks/handlers.py. Both are Blocker 2 -- the
    sessions refactor removes them, and this function with them.

    Until then this raises rather than resolving, because neither alternative is
    safe: extraction_model() would hand a LitellmModel object to the OpenAI
    client, and the bare half of an 'anthropic/...' name is a model OpenAI has
    never heard of. Both fail confusingly at request time; this fails clearly at
    the call, naming the reason.
    """
    provider, bare = split_provider(env.EXTRACTION_MODEL)
    if provider != 'openai':
        raise ValueError(
            f'EXTRACTION_MODEL={env.EXTRACTION_MODEL!r} routes to {provider!r}, but '
            f'this path calls the OpenAI Responses API directly for its '
            f'server-side conversation state. It needs the client-side sessions '
            f'refactor before a non-OpenAI extraction model can be configured.'
        )
    return bare
