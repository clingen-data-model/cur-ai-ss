"""Resolve configured model names into values the OpenAI SDK can consume.

Every configured model name carries a LiteLLM-style provider prefix
('openai/gpt-5.6-luna', 'anthropic/claude-sonnet-5'); bare names are rejected so
the provider is always explicit in config.

'openai/' resolves to the plain model string, which both the agents SDK's
default provider (the Responses API) and the OpenAI client take as-is.

Any other provider has nowhere to route yet, and the settings validator rejects
it at load -- so by the time anything here runs, the provider is routable. The
raise below is a backstop for that invariant, not the primary guard: it must not
become the thing that catches an unroutable name, because both vision tools call
into this from inside a function_tool body, where the SDK's default error
handler would turn the exception into text for the model rather than failing the
run. Widening ROUTABLE_PROVIDERS is the model-routing work, and it belongs with
a matching branch here.
"""

from lib.core.environment import env
from lib.core.model_names import ROUTABLE_PROVIDERS, split_provider


def extraction_model() -> str:
    """The model every text-extraction agent runs on."""
    return resolve_model(env.EXTRACTION_MODEL)


def vlm_model() -> str:
    """The model the vision tools run on."""
    return resolve_model(env.VLM_MODEL)


def resolve_model(name: str) -> str:
    provider, bare = split_provider(name)
    if provider == 'openai':
        return bare
    raise ValueError(
        f'Model {name!r} names provider {provider!r}, which has no route yet. '
        f'Supported: {", ".join(sorted(ROUTABLE_PROVIDERS))}.'
    )
