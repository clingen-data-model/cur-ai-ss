"""Resolve configured model names into agents-SDK model values.

Every configured model name carries a LiteLLM-style provider prefix
('openai/gpt-5.6-luna', 'anthropic/claude-sonnet-5'); bare names are rejected
so the provider is always explicit in config.

'openai/' names resolve to the plain model string so the SDK's default OpenAI
provider (the Responses API) keeps serving them. This is deliberate for now:
the pipeline still relies on the Responses API's server-side conversation_id
for additional-context reruns, and LitellmModel silently ignores that
parameter. Once client-side sessions replace conversation_id, 'openai/' can
route through LiteLLM like every other provider and this special case goes.
"""

from agents.extensions.models.litellm_model import LitellmModel
from agents.models.interface import Model

from lib.core.environment import env

OPENAI_PREFIX = 'openai/'
ANTHROPIC_PREFIX = 'anthropic/'


def extraction_model() -> Model | str:
    """The model every text-extraction agent runs on."""
    return resolve_model(env.EXTRACTION_MODEL)


def resolve_model(name: str) -> Model | str:
    provider, bare = split_provider(name)
    if provider == 'openai':
        return bare
    if provider == 'anthropic':
        return LitellmModel(name, api_key=env.ANTHROPIC_API_KEY)
    # Any other LiteLLM provider: rely on its ambient env-var credentials.
    return LitellmModel(name)


def split_provider(name: str) -> tuple[str, str]:
    """('openai', 'gpt-5.6-luna') from 'openai/gpt-5.6-luna'; rejects bare names."""
    provider, sep, bare = name.partition('/')
    if not sep or not provider or not bare:
        raise ValueError(
            f'Model name {name!r} must carry a provider prefix, '
            f"e.g. 'openai/gpt-5.6-luna' or 'anthropic/claude-sonnet-5'."
        )
    return provider, bare


def provider_api_key(name: str) -> str | None:
    """The configured API key for the provider a model name belongs to."""
    provider, _ = split_provider(name)
    if provider == 'openai':
        return env.OPENAI_API_KEY
    if provider == 'anthropic':
        return env.ANTHROPIC_API_KEY
    return None
