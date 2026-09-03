"""Resolve configured model names into agents-SDK model values.

A provider-prefixed LiteLLM name ('anthropic/claude-sonnet-5') becomes a
LitellmModel routed to that provider; a bare name ('gpt-5.6-luna') is returned
as a plain string and handled by the SDK's default OpenAI provider — which is
what keeps the pipeline env-switchable between providers.
"""

from agents.extensions.models.litellm_model import LitellmModel
from agents.models.interface import Model

from lib.core.environment import env


def extraction_model() -> Model | str:
    """The model every text-extraction agent runs on."""
    return resolve_model(env.EXTRACTION_MODEL)


def resolve_model(name: str) -> Model | str:
    if name.startswith('anthropic/'):
        return LitellmModel(name, api_key=env.ANTHROPIC_API_KEY)
    if '/' in name:
        # Some other LiteLLM provider: rely on its ambient env-var credentials.
        return LitellmModel(name)
    return name
