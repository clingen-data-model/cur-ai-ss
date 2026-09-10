"""Parsing for the '<provider>/<model>' names in EXTRACTION_MODEL / VLM_MODEL.

Both the settings validator and lib.agents.model_factory need this parse and the
set of providers that can actually be routed. model_factory imports `env`, so
this lives in lib.core where neither has to import the other -- and, more to the
point, so the two cannot drift apart: a provider the validator accepts is by
construction one the factory can route.
"""

# Providers lib.agents.model_factory can resolve today. Widening this set is the
# model-routing work. The settings validator rejects anything outside it, so an
# unroutable name fails at settings load -- before any agent is constructed, and
# well before a vision tool could turn the error into text for the model.
ROUTABLE_PROVIDERS = frozenset({'openai'})


def split_provider(name: str) -> tuple[str, str]:
    """('openai', 'gpt-5.6-luna') from 'openai/gpt-5.6-luna'; rejects bare names."""
    provider, sep, bare = name.partition('/')
    if not sep or not provider or not bare:
        raise ValueError(
            f'Model name {name!r} must carry a provider prefix, '
            f"e.g. 'openai/gpt-5.6-luna' or 'anthropic/claude-sonnet-5'."
        )
    return provider, bare
