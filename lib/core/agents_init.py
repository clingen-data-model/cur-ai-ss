"""One-time agents-SDK process configuration.

The SDK uploads traces to OpenAI's servers by default; with models now
routable to other providers via LiteLLM, tracing is disabled outright so no
run data leaves the configured provider.
"""

from agents import set_tracing_disabled


def init_agents_sdk() -> None:
    set_tracing_disabled(True)
