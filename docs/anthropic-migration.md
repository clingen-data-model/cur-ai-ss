# Anthropic migration: what's left after LiteLLM routing

Status as of 2026-09-09, written against the `litellm-model-routing` branch (PR #137).

Findings below marked **confirmed** were verified by running the locked
dependencies (`litellm==1.83.0`, `openai-agents==0.7.0`) — no API key needed.
Line citations are into `.venv/lib/python3.12/site-packages` at those versions
and will drift if either is bumped. Claims about what Anthropic accepts come from
`platform.claude.com/docs/en/build-with-claude/structured-outputs`.

## Where we are

PR #137 builds a seam, not a migration. `lib/agents/model_factory.resolve_model()`
turns a `<provider>/<model>` name into either a bare string (OpenAI, served by the
SDK's default provider) or a `LitellmModel`. All 17 agents take
`model=extraction_model()`; both VLM tools go through `lib/agents/vision.vlm_describe()`.
Defaults still name OpenAI models, so behavior is unchanged.

The `openai/` special case in `resolve_model()` exists because `LitellmModel`
ignores `conversation_id` — **confirmed**, it is literally annotated
`conversation_id: str | None = None,  # unused` at `litellm_model.py:161` and
`:271`, and never referenced in either body.

## Blocker 1: structured output collapses the tool loop (highest risk)

This was filed as a schema-conformance question. It is not. The schemas are fine;
the *delivery mechanism* is broken for our target models.

LiteLLM decides between Anthropic's native structured outputs and a
forced-tool-call emulation using a **hardcoded model-substring allowlist**
(`llms/anthropic/chat/transformation.py`, around `:995`-`:1010`): `sonnet-4.5`,
`sonnet-4-6`, `opus-4.1`, `opus-4.5`, `opus-4.6`, `opus-4.7` and spelling
variants. **`claude-sonnet-5`, `claude-opus-5` and `claude-fable-5-1` match
nothing in that list**, so all three of our intended targets fall to the
emulation branch, which:

- appends a synthetic tool named `json_tool_call` to whatever tools are already
  there — `_add_tools_to_optional_params` appends, it does not replace; and
- sets `tool_choice = {"name": "json_tool_call", "type": "tool"}`, forcing it
  (`:1017`-`:1019`) — but **only when thinking is disabled**.

**Confirmed** by running the real agents' real output types through
`litellm.utils.get_optional_params(model='claude-sonnet-5', custom_llm_provider='anthropic', ...)`:

```
hpo_linking_agent                strict=True defs=True ref=True tools=4
mondo_linking_agent              strict=True defs=True ref=True tools=9
patient_phenotype_linking_agent  strict=True defs=True ref=True tools=0
variant_harmonization_agent      strict=True defs=True ref=True tools=7
patient_extraction_agent         strict=True defs=True ref=True tools=0

tool_choice: {"name": "json_tool_call", "type": "tool"}
json_mode: True
num tools sent: 2
  tool='json_tool_call'   has_$ref=True  has_$defs=True
  tool='search_hpo_terms' has_$ref=False has_$defs=False
```

Two independent defects fall out of that:

**a) The tool-using agents lose their tool loop.** `json_tool_call` is sent
*alongside* `search_hpo_terms`, with `tool_choice` compelling the JSON tool. The
model cannot reach the search tool. This raises no error — the task succeeds and
returns well-formed structured output derived from zero ontology lookups. Silently
worse extraction, no failed task, no exception.

The damage is confined to the agents that have tools, and it is worst where the
loop matters most: MONDO linking has 9 tools, variant harmonization 7, HPO linking
4 (and is configured for `max_turns=15`; MONDO for 25). The 8 zero-tool agents are
*fine* on this path — a single forced tool is precisely Anthropic's documented JSON
mode.

**b) `$defs`/`$ref` are forwarded unresolved — but this turns out to be harmless.**
All output types emit them, because `ensure_strict_json_schema`
(`agents/agent_output.py:113`) applies strict rules *through* refs without inlining
them. The emulation path does a bare `_input_schema.update(json_schema)`
(`transformation.py:1109`) and unpacks nothing, where the native path deep-copies
and calls `unpack_defs` (`:805`, `:811`).

Per Anthropic's structured-outputs documentation, **internal `$ref`/`$defs` are
supported**; only *external* refs (`http://...`) are not. LiteLLM's `unpack_defs`
comment refers to the external case. **Confirmed** that every one of our schemas
uses internal refs only, and that none of them carry any of the unsupported
keywords (`minimum`, `maximum`, `multipleOf`, `minLength`, `maxLength`, `pattern`,
`maxItems`, `uniqueItems`, or a `minItems` other than 0/1) — a scan across 13
agents came back completely clean. So no Pydantic model in this repo needs to
change.

### This is a LiteLLM gap, not an Anthropic limitation

Anthropic natively supports exactly the shape this pipeline needs:

- **Structured outputs and tool use compose in one request.** Claude either calls a
  tool (`stop_reason: "tool_use"`) or returns structured JSON (`end_turn`),
  deciding per turn. No forced `tool_choice`, so the tool loop survives intact.
- `claude-sonnet-5` is on the supported-model list, as are `claude-opus-5` and
  `claude-fable-5-1`.
- The current parameter is `output_config.format`; `output_format` — which is what
  LiteLLM's native branch emits — is deprecated but accepted during a transition
  period.

So the capability exists, our schemas qualify for it, and the only obstacle is
LiteLLM's routing. **Confirmed** that the gate (`transformation.py:988`-`:1005`) is
a bare hardcoded set of model-name substrings with no model-registry lookup, no
config flag, and no override hook — so `litellm.register_model` cannot reach it
either. The set is stale on LiteLLM `main` as well, so there is no version to
upgrade to.

Ways out, roughly in order of appeal:

1. Upstream a patch to LiteLLM adding the current model names to that set (or
   making it consult `supports_response_schema` in the model registry). Three
   lines, and correct for everyone.
2. Carry a small local shim overriding that one branch until upstream lands. This
   is the only option that unblocks `EXTRACTION_MODEL` without touching agent code.
3. Enable thinking. Per `:1017` no `tool_choice` is set when thinking is enabled,
   so the model is merely nudged toward the output tool and can still reach the
   real tools. Keeps the loop alive, but stays on the emulation path and is
   non-deterministic.
4. Stop using `output_type` on the tool-using agents and parse a final message
   instead. Largest change, provider-independent.

`claude-fable-5-1` additionally rejects forced `tool_choice` outright, so it cannot
be `EXTRACTION_MODEL` on the emulation path at all. Worth rejecting that
combination in `Env` validation rather than discovering it in production.

Two smaller notes: structured outputs add a system prompt, so enabling them shifts
input token counts and invalidates any existing prompt cache for the thread; and
compiled grammars are cached for 24h but invalidated by a change to the schema *or
to the set of tools in the request*.

## Blocker 2: `conversation_id` → sessions

`lib/tasks/handlers.py` repeats the same six-step dance in ~12 handlers: read
`task.conversation_id`, call `ensure_conversation_id()`, branch on
`additional_context`, `Runner.run(..., conversation_id=...)`, persist the id back.

Sessions and `conversation_id` are mutually exclusive within a run, so this is a
swap, not a layering. Two independently verifiable steps:

1. Replace `conversation_id=X` with `session=OpenAIConversationsSession(conversation_id=X)`.
   **Confirmed** that its constructor accepts an existing id
   (`agents/memory/openai_conversations_session.py:23`, created lazily when
   `None`) — so this step is behavior-preserving on our already-persisted ids,
   and it collapses 12 copies into one helper.
2. Swap the implementation for a local session.

### Two constraints on step 2

**`SQLAlchemySession` needs an async engine.** Its constructor
(`agents/extensions/memory/sqlalchemy_session.py:59`) is
`(session_id, *, engine: AsyncEngine, create_tables=False, sessions_table='agent_sessions', messages_table='agent_messages')`.
`AsyncEngine` means an async driver — `sqlite+aiosqlite://`. Our `lib/api/db.py`
engine is sync and **cannot be reused**; this means adding `aiosqlite` and running
a second, parallel engine against the same file.

**Its schema trips our known SQLite hazard.** `agent_messages` → `agent_sessions`
carries `ondelete="CASCADE"`. `create_tables` defaults to `False`, so these want
an Alembic migration — see the `batch_alter_table` + `PRAGMA foreign_keys` rules in
`CLAUDE.md`, and the June 2026 incident that motivated them.

### Storage design worth deciding first

`SQLAlchemySession` persists full transcripts. With the paper markdown in every
initial message and roughly 40 agent runs per paper, that grows fast.

Turn 0 is deterministically reconstructible — it is
`format_paper_context(fulltext_md(paper_id, supplement_format), gene_symbol)` plus
the agent's instructions, all already in the database. A custom session storing
only assistant outputs and follow-up turns, rebuilding turn 0 on demand, would be
far lighter and would sidestep both constraints above.

The tradeoff: we lose the intermediate tool-call transcript the Conversations API
currently replays. For a follow-up that asks the model to revisit its own
conclusion, replaying `[initial message, final output, follow-up]` is probably
enough — but that is a judgment call.

## Blocker 3: prompt caching

OpenAI caches automatically. Anthropic requires explicit `cache_control`
breakpoints. HPO linking runs `max_turns=15` and MONDO 25, and every turn re-sends
the full paper markdown, so this is real money.

**The seam exists and is confirmed.** LiteLLM accepts a top-level
`cache_control_injection_points` parameter, consumed by
`integrations/anthropic_cache_control_hook.py:55`. Injection points are shaped
`{"location": "message", "role": ..., "index": int|str (negatives allowed), "control": {"type": "ephemeral"}}`.
`cache_control` keys inside message content blocks are honored too. Nothing is
automatic — it must be requested.

And it reaches LiteLLM through the agents SDK: `ModelSettings.extra_args` is
splatted into the `litellm.acompletion` call as top-level kwargs
(`litellm_model.py:475`-`:476`). So:

```python
ModelSettings(extra_args={'cache_control_injection_points': [
    {'location': 'message', 'role': 'user', 'control': {'type': 'ephemeral'}},
]})
```

There is **no** per-message or per-content-block hook in the SDK — messages are
built wholly by the converter — so `extra_args` is the only seam. Note the hook
deep-copies messages on every call.

Remaining unknown: whether that actually yields nonzero cache reads in practice,
and whether the 5-minute default TTL survives our inter-task gaps or needs the
1-hour TTL. Needs a live key.

## Correction: `log_cache_metrics` needs no change

An earlier revision of this doc claimed the metric would silently report `0.0%` on
Anthropic and had to be fixed before any flip. **That was wrong.**
`litellm_model.py:212`-`:214` translates litellm's
`prompt_tokens_details.cached_tokens` into the SDK's
`input_tokens_details.cached_tokens` — exactly what `log_cache_metrics` already
reads. litellm's `prompt_tokens` also already includes cached tokens, so the
percentage denominator is right too. No change required.

## The VLM path is already migratable

`vlm_describe` calls `litellm.completion` directly — no `conversation_id`, no
structured output, no tools. It is the one seam in PR #137 that touches none of
the three blockers, so flipping `VLM_MODEL` is a one-line env change that buys real
production signal (auth, latency, refusal handling, billing shape) while the rest
proceeds.

Two things to confirm first, since either could invalidate the target:

- **Data retention.** `claude-fable-5-1` requires 30-day retention and is not
  available under zero data retention without Anthropic's express authorization.
- **Cost.** Fable 5.1 is $10/$50 per MTok against Sonnet 5 at $2/$10. Worth
  checking whether Sonnet 5 clears the bar on pedigrees and tables before
  committing to the premium tier.

## Observability gap

PR #137 disables tracing (`lib/core/agents_init.py`) and drops both
`RunConfig(trace_metadata)` blocks — `paper_id`, `phenotype_id`, `concept`,
`disease_text`, `gene_symbol`. Disabling tracing is right, since the SDK uploads to
OpenAI by default. But it removes run-level observability immediately before the
migration where we would most want to compare runs across providers. Structured
logging off `result.raw_responses` would fill it cheaply.

Worth pairing with a check that the tool loop actually ran — given Blocker 1a, an
HPO linking run that makes zero tool calls is the failure signature to alarm on.

## Dependency pin hazard

`pyproject.toml` pins `litellm>=1.75` with no upper bound, and the allowlist that
decides native-vs-emulated structured output is version-specific and undocumented.
A routine resolver bump can silently move every agent between the two paths in
either direction. This wants an upper bound.

## What still needs a live API key

Everything above is settled. These are not:

1. Does a shimmed native path actually work end-to-end — `output_config.format`
   (or LiteLLM's `output_format`) plus real tools, with the agents SDK parsing the
   result and the tool loop still running? This is the go/no-go for
   `EXTRACTION_MODEL`. The documentation says yes; nobody has run it here.
2. Does `claude-fable-5-1` actually 400 on forced `tool_choice`? One call.
3. Does `cache_control_injection_points` via `extra_args` produce nonzero
   `cache_read_input_tokens`, and does the default TTL survive our task gaps? Two
   calls plus a gap.
4. Fable 5.1 vs Sonnet 5 quality on pedigree and table images. Needs a real eval
   set, not a spike.

Schema conformance is *no longer* on this list — Anthropic's documented
restrictions plus the offline scan settle it without a call.

Note LiteLLM authenticates with a raw `x-api-key`; an `ant auth login` OAuth
profile will not be picked up. This needs an actual `ANTHROPIC_API_KEY`.

## Suggested order

1. Merge PR #137. CI is green, no conflicts; it needs an approving review.
2. Pin an upper bound on `litellm`.
3. Flip `VLM_MODEL` to Anthropic behind the retention check — real signal, and it
   depends on none of the blockers.
4. Resolve Blocker 1 — the go/no-go for `EXTRACTION_MODEL`. Shim the LiteLLM gate
   locally to unblock, and upstream the fix in parallel so the shim is temporary.
5. Sessions refactor, in the two steps above.
6. Caching, once a model is actually running on Anthropic.

## Reproducing the offline findings

```bash
ENV_FILE=.env.test uv run python - <<'PY'
import importlib, json
from agents.agent_output import AgentOutputSchema
from litellm.utils import get_optional_params

mod = importlib.import_module('lib.agents.hpo_linking_agent')
schema = AgentOutputSchema(mod.agent.output_type).json_schema()

op = get_optional_params(
    model='claude-sonnet-5', custom_llm_provider='anthropic',
    response_format={'type': 'json_schema', 'json_schema': {
        'name': 'final_output', 'strict': True, 'schema': schema}},
    tools=[{'type': 'function', 'function': {
        'name': 'search_hpo_terms', 'description': 'search',
        'parameters': {'type': 'object', 'properties': {'q': {'type': 'string'}},
                       'required': ['q']}}}],
)
print('tool_choice:', json.dumps(op.get('tool_choice')))
print('tools sent :', [t.get('name') or t['function']['name'] for t in op.get('tools') or []])
print('has $ref   :', '"$ref"' in json.dumps(op.get('tools')))
PY
```
