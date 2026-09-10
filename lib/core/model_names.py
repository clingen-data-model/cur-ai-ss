"""Parsing for the '<provider>/<model>' names in EXTRACTION_MODEL / VLM_MODEL.

Both the settings validator and lib.agents.model_factory need this parse and the
set of providers that can actually be routed. model_factory imports `env`, so
this lives in lib.core where neither has to import the other -- and, more to the
point, so the two cannot drift apart: a provider the validator accepts is by
construction one the factory can route.
"""

# Providers lib.agents.model_factory can resolve. 'openai' goes to the agents
# SDK's default provider; 'anthropic' goes through LiteLLM. The settings
# validator rejects anything outside this set, so an unroutable name fails at
# settings load -- before any agent is constructed, and well before a vision
# tool could turn the error into text for the model.
#
# Adding a provider here means adding a branch to resolve_model and an entry to
# PROVIDER_KEY_SETTINGS below; test_every_routable_provider_resolves fails if
# the first is forgotten, and validate_models raises if the second is.
ROUTABLE_PROVIDERS = frozenset({'openai', 'anthropic'})

# The Env setting each provider draws its credentials from. LiteLLM would also
# read an ambient ANTHROPIC_API_KEY on its own, but routing the key through Env
# keeps one source of truth and lets the validator refuse a model whose key is
# missing rather than failing on the first API call.
PROVIDER_KEY_SETTINGS: dict[str, str] = {
    'openai': 'OPENAI_API_KEY',
    'anthropic': 'ANTHROPIC_API_KEY',
}


def split_provider(name: str) -> tuple[str, str]:
    """('openai', 'gpt-5.6-luna') from 'openai/gpt-5.6-luna'; rejects bare names."""
    provider, sep, bare = name.partition('/')
    if not sep or not provider or not bare:
        raise ValueError(
            f'Model name {name!r} must carry a provider prefix, '
            f"e.g. 'openai/gpt-5.6-luna' or 'anthropic/claude-sonnet-5'."
        )
    return provider, bare
