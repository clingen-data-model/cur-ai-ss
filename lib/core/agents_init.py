from agents import set_tracing_disabled


def init_agents_sdk() -> None:
    """One-time agents-SDK process configuration. The SDK exports full trace
    data -- including paper/patient content -- to OpenAI's servers by default
    on every Runner.run call, regardless of which provider actually served the
    request. Disabled outright, process-wide, so no run data leaves the
    configured provider. See docs/anthropic-migration.md's "Observability gap".
    """
    set_tracing_disabled(True)
