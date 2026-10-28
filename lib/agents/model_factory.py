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

import logging
from typing import Any

import litellm
from agents import Agent, ModelSettings
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

logger = logging.getLogger(__name__)

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


def agent_on_tier(agent: Agent, budget: bool) -> Agent:
    """The agent a task's run uses: ``agent`` itself for an ordinary run,
    or, when the task's ``budget_model`` flag is set, the same agent on
    ``EXTRACTION_BUDGET_MODEL``.

    A clone rather than a ``RunConfig`` override: ``ModelSettings.resolve``
    merges ``extra_args`` dict-wise, so an override could never *remove* the
    ``output_config.effort`` an agent sets, and a budget model that rejects
    the parameter would 400 on every call. The clone rebuilds its settings
    for the budget model from scratch, carrying the agent's effort across
    only when ``model_settings_for`` finds that model accepts it. The agents
    are module-level singletons built on ``extraction_model()``; a per-run
    clone leaves them as they were for the next task.

    Only the handlers whose agent runs on ``EXTRACTION_MODEL`` call this.
    Linking (``LINKING_MODEL``) and vision (``VLM_MODEL``) are configured
    separately and a quick run does not move them. With no
    ``EXTRACTION_BUDGET_MODEL`` configured a budget run is an ordinary run.
    """
    name = env.EXTRACTION_BUDGET_MODEL
    if not budget or name is None:
        return agent
    extra = agent.model_settings.extra_args or {}
    effort = (extra.get('output_config') or {}).get('effort')
    logger.info(f'{agent.name}: running on the budget model {name}')
    return agent.clone(
        model=resolve_model(name),
        model_settings=model_settings_for(name, effort=effort),
    )


def linking_model() -> Model | str:
    """The model the ontology-linking agents (HPO, MONDO) run on:
    ``LINKING_MODEL``, which a deployment may set cheaper than
    ``EXTRACTION_MODEL`` (see lib/core/environment.py for why)."""
    return resolve_model(env.LINKING_MODEL)


def linking_model_settings() -> ModelSettings:
    """Model settings for the ontology-linking agents: their model's cache
    breakpoints at low effort, for the reasons ``decision_model_settings``
    gives."""
    return model_settings_for(env.LINKING_MODEL, effort='low')


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


class ModelDeclined(Exception):
    """The provider's safety classifier declined the request: before the model
    answered it, or partway through the answer.

    Anthropic returns this as a normal HTTP 200 with ``stop_reason:
    "refusal"``, the content empty (a refusal before output) or cut off (a
    classifier that reads the output as it streams, such as the
    ``reasoning_extraction`` guard lib/agents/model_facing.py exists for);
    litellm reports either as ``finish_reason == "content_filter"`` and drops
    the category. The agents SDK's LitellmModel reads
    only the message, which here has no text and no tool call, so it builds
    an empty turn -- and the run loop treats an empty turn as "run again" with
    the same input, which gets the same refusal, until max_turns ends the run
    as MaxTurnsExceeded. Every one of those turns is a billed request in the
    categories Anthropic bills before output (bio, among others). Seen live
    2026-10-19: Fable 5.1's bio classifier refused the table-correction judge
    call for paper 106 table 2 (an enzyme-activity table), ten times, then
    failed the paper's PDF parse with a message that said nothing about why.

    Raising here instead fails the run on the first refusal with the reason
    in the message. A caller that has a defined outcome for "the model would
    not say" (table correction leaves the table unrecovered) catches it;
    anywhere else the task fails once with a readable error.
    """

    def __init__(self, model: str, finish_reason: str) -> None:
        self.model = model
        self.finish_reason = finish_reason
        super().__init__(
            f'{model} declined the request (finish_reason={finish_reason}); '
            f"the provider's safety classifier refused it, before or during the answer"
        )


class _DeclineAwareLitellmModel(LitellmModel):
    """LitellmModel that raises ModelDeclined on a classifier refusal rather
    than returning the empty turn the run loop would retry (see ModelDeclined).

    Overrides the private ``_fetch_response`` because it is the one place the
    litellm response is still whole; ``get_response`` has dropped the finish
    reason by the time it returns. Pinned to the locked agents SDK (0.7.0):
    test_a_refusal_raises_model_declined exercises the real ``get_response``
    path, so an upgrade that renames or reshapes the hook fails there rather
    than silently restoring the loop.
    """

    async def _fetch_response(self, *args: Any, **kwargs: Any) -> Any:
        response = await super()._fetch_response(*args, **kwargs)
        if isinstance(response, litellm.types.utils.ModelResponse):
            choices = response.choices
            first = choices[0] if choices else None
            if getattr(first, 'finish_reason', None) == 'content_filter':
                raise ModelDeclined(self.model, 'content_filter')
        return response


def resolve_model(name: str) -> Model | str:
    provider, bare = split_provider(name)
    if provider == 'openai':
        return bare
    if provider in ROUTABLE_PROVIDERS:
        return _DeclineAwareLitellmModel(name, api_key=provider_api_key(name))
    raise ValueError(
        f'Model {name!r} names provider {provider!r}, which has no route yet. '
        f'Supported: {", ".join(sorted(ROUTABLE_PROVIDERS))}.'
    )


def provider_api_key(name: str) -> str | None:
    """The configured API key for the provider a model name belongs to."""
    provider, _ = split_provider(name)
    setting = PROVIDER_KEY_SETTINGS.get(provider)
    return getattr(env, setting) if setting else None
