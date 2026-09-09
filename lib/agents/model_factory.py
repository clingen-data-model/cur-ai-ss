"""Resolve configured model names into values the OpenAI SDK can consume.

Every configured model name carries a LiteLLM-style provider prefix
('openai/gpt-5.6-luna', 'anthropic/claude-sonnet-5'); bare names are rejected so
the provider is always explicit in config.

'openai/' resolves to the plain model string, which both the agents SDK's
default provider (the Responses API) and the OpenAI client take as-is. Any other
provider parses and validates here but has nowhere to route yet, so it raises --
at agent construction, which for the module-level agents means process start,
rather than partway through a pipeline run. Filling in those branches is the
model-routing work; this module is where it lands.
"""

from lib.core.environment import env


def extraction_model() -> str:
    """The model every text-extraction agent runs on."""
    return resolve_model(env.EXTRACTION_MODEL)


def vlm_model() -> str:
    """The model the vision tools run on."""
    return resolve_model(env.VLM_MODEL)


def resolve_model(name: str) -> str:
    provider, bare = split_provider(name)
    if provider != 'openai':
        raise ValueError(
            f'Model {name!r} names provider {provider!r}, which has no route yet. '
            f"Only 'openai/' models are supported until model routing lands."
        )
    return bare


def split_provider(name: str) -> tuple[str, str]:
    """('openai', 'gpt-5.6-luna') from 'openai/gpt-5.6-luna'; rejects bare names."""
    provider, sep, bare = name.partition('/')
    if not sep or not provider or not bare:
        raise ValueError(
            f'Model name {name!r} must carry a provider prefix, '
            f"e.g. 'openai/gpt-5.6-luna' or 'anthropic/claude-sonnet-5'."
        )
    return provider, bare
