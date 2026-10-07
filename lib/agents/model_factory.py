"""Resolve configured model names into values the agents SDK can consume.

Every configured model name carries a LiteLLM-style provider prefix
('openai/gpt-5.6-luna', 'anthropic/claude-sonnet-5'); bare names are rejected so
the provider is always explicit in config.

'openai/' resolves to the plain model string, which the agents SDK's default
provider (the Responses API) takes as-is, rather than routing through
LitellmModel like every other provider.

This used to be load-bearing: the additional-context rerun feature relied on
the Responses API's server-side conversation_id, which LitellmModel ignores
entirely (it is annotated `# unused` at litellm_model.py:161 and :271 in the
locked 0.7.0), so routing OpenAI through LiteLLM would have silently dropped
the conversation history rather than fail. That dependency is gone --
lib.tasks.agent_session now gives every task its own local SQLiteSession,
provider-agnostic -- so nothing here still requires 'openai/' to bypass
LiteLLM. Left in place because collapsing it changes how every OpenAI call is
made, which deserves its own change and its own testing, not a side effect of
this one.

Any other provider routes through LitellmModel. The settings validator rejects
an unroutable provider at load, so by the time anything here runs the provider
is routable; the raise below is a backstop for that invariant, not the primary
guard. It must not become the thing that catches an unroutable name, because
both vision tools call into this from inside a function_tool body, where the
SDK's default error handler would turn the exception into text for the model
rather than failing the run.
"""

import litellm
from agents import ModelSettings
from agents.extensions.models.litellm_model import LitellmModel
from agents.models.interface import Model
from litellm.llms.anthropic.chat.transformation import AnthropicConfig

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

# Fallback entries for models Anthropic has released that litellm may not know.
# litellm loads its model table from the copy bundled with the locked release,
# then replaces it with the one it fetches from GitHub at process start (and
# keeps the bundled copy if that fetch fails). A release's bundled copy predates
# any model launched after it, so whether a new model is known can depend on
# whether GitHub was reachable at startup. Unknown means litellm reports no
# native structured output, so it emulates JSON output with a forced
# tool_choice -- which, next to an agent's real tools, means the model can never
# call them and the task still "succeeds" (docs/anthropic-migration.md, Blocker
# 1) -- and no `output_config.effort` support, so `model_settings_for` silently
# drops the effort an agent asks for.
#
# This only declares facts to litellm, in this process; it sends nothing and
# registers nothing upstream. An entry litellm already has is left alone, so
# these only matter when the fetch fails or the bundled copy is all there is;
# delete one when a litellm bump bundles the model.
#
# claude-haiku-5-5 (released 2026-10-07): 1M context, 128K output, adaptive
# thinking. Upstream added its own entry the same day, with tiered pricing; the
# prices here are only the under-100k-token-prompt rates ($0.10/$0.50 per MTok),
# so cost tracking on this fallback undercounts calls with larger prompts.
_UNMAPPED_MODELS: dict[str, dict] = {
    'claude-haiku-5-5': {
        'litellm_provider': 'anthropic',
        'mode': 'chat',
        'max_tokens': 128_000,
        'max_input_tokens': 1_000_000,
        'max_output_tokens': 128_000,
        'input_cost_per_token': 1e-07,
        'output_cost_per_token': 5e-07,
        'supports_native_structured_output': True,
        'supports_response_schema': True,
        'supports_output_config': True,
        'supports_reasoning': True,
        'supports_vision': True,
        'supports_function_calling': True,
        'supports_tool_choice': True,
        'supports_prompt_caching': True,
    },
}


def _register_unmapped_models() -> None:
    missing = {
        name: facts
        for name, facts in _UNMAPPED_MODELS.items()
        if name not in litellm.model_cost
    }
    if missing:
        litellm.register_model(missing)


_register_unmapped_models()


def extraction_model() -> Model | str:
    """The model every text-extraction agent runs on."""
    return resolve_model(env.EXTRACTION_MODEL)


def extraction_model_settings() -> ModelSettings:
    """Model settings every text-extraction agent runs with."""
    return model_settings_for(env.EXTRACTION_MODEL)


def decision_model_settings() -> ModelSettings:
    """Model settings for agents choosing among a small set of options rather
    than extracting open-ended structured data from a paper -- HPO/MONDO
    linking, segregation classification. These are closer to classification
    than reasoning-heavy extraction, so they hold up fine at lower effort, and
    lower effort also means fewer, more consolidated tool calls -- directly
    addressing the multi-turn ontology-walk cost these agents are prone to
    (see docs/anthropic-migration.md's cost-reduction notes).
    """
    return model_settings_for(env.EXTRACTION_MODEL, effort='low')


def model_settings_for(name: str, *, effort: str | None = None) -> ModelSettings:
    """Prompt-cache breakpoints for a configured model, gated on provider.

    Anthropic only: ModelSettings.extra_args is splatted as top-level kwargs
    into whichever API the model resolves to, including the OpenAI Responses
    call the agents SDK's default provider makes. Sending
    cache_control_injection_points there is not a no-op -- OpenAI does not know
    the parameter, so an openai/ model gets the empty ModelSettings() the type
    requires (Agent.__post_init__ rejects None) rather than these breakpoints.
    The same is true of `effort`: `output_config.effort` is meaningless outside
    Anthropic, so it is only ever set here, never as a provider branch inside
    an agent -- a fixed, per-agent choice about how hard that agent's task
    warrants thinking, not a workaround for what today's provider can't do.
    Not every Anthropic model accepts it, though -- confirmed live,
    'anthropic/claude-haiku-4-5-20251001' 400s on any `output_config` at all
    ("This model does not support the effort parameter"), while Sonnet 5,
    Opus 5 and Fable 5.1 all accept it. litellm already carries this as a
    capability flag per model (`AnthropicConfig._model_supports_effort_param`,
    checked the same way its `supports_native_structured_output` flag settled
    Blocker 1 in docs/anthropic-migration.md), so effort is gated on that
    rather than a hardcoded model-name list here.

    Three breakpoints, one per shared block of the input that
    ``lib.tasks.handlers.paper_input`` builds. Index 1 is the paper block,
    right after the system message the SDK inserts at index 0: the same bytes
    for every agent on that paper, so one write serves the whole pipeline.
    Index 2 is the agent's instructions (plus the manual-output schema
    directive, for the two agents that need one): the same for every run of
    one agent on that paper, written
    once by the first run (which the worker's fan-out gate makes happen
    alone) and read by the rest. Index -1 is the message being extended: the
    run's data on the first turn, then tool results, repair turns and
    follow-ups. Absolute positions, not roles: a thread that has accumulated
    follow-ups has several user messages, and role targeting would stamp
    them all. An input with no data item has its instructions at both 2 and
    -1 and an agent with no paper has one message at 1 and -1; litellm skips
    a message already carrying cache_control, and logs and skips an index
    past the end, so those collapse. No 'system' point: every agent's
    instructions constant is the ~120-char base prompt, far below the
    minimum cacheable block, so it could never write anything.

    History (docs/anthropic-migration.md, "Prompt caching, second pass"):
    before 2026-09-30 the points were 'system' and -1 with the paper inlined
    into one message per call, so every run wrote a unique-prefix entry at
    the 1h write price and nothing ever read one. PR #334 split the paper
    out (index 1); paper 80 then read 44% of a demographics call and 62% of
    a phenotype call, the rest being the agent's constant text placed after
    the run's data. This split moves that text before the data (index 2).
    """
    provider, bare = split_provider(name)
    if provider != 'anthropic':
        return ModelSettings()
    extra_args: dict = {
        'cache_control_injection_points': [
            {'location': 'message', 'index': 1, 'control': _CACHE_CONTROL},
            {'location': 'message', 'index': 2, 'control': _CACHE_CONTROL},
            {'location': 'message', 'index': -1, 'control': _CACHE_CONTROL},
        ]
    }
    if effort is not None and AnthropicConfig._model_supports_effort_param(
        bare, provider
    ):
        extra_args['output_config'] = {'effort': effort}
    return ModelSettings(extra_args=extra_args)


def chat_model() -> Model | str:
    """The model the chat agent runs on."""
    return resolve_model(env.CHAT_MODEL)


def chat_model_settings() -> ModelSettings:
    """Chat's model settings -- just the prompt-cache breakpoints, same as
    every other agent.

    This used to also request Anthropic Fast mode ('speed': 'fast'). Verified
    live against production and reverted: our Anthropic org has a 0
    fast-mode-input-tokens-per-minute limit, so every Fast mode request 429s
    outright (litellm.RateLimitError, "This request would exceed your rate
    limit of 0 fast mode input tokens per minute") regardless of prompt size --
    not a usage-based limit that headroom or backoff would fix, but Fast mode
    not being provisioned on this account's plan at all. Revisit only after
    confirming with Anthropic that the org's plan grants Fast mode capacity.
    """
    return model_settings_for(env.CHAT_MODEL)


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
