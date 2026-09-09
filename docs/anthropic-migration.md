# Anthropic migration: what's left after LiteLLM routing

Status as of 2026-09-09, written against the `litellm-model-routing` branch (PR #137).

Findings below marked **confirmed** were verified by running the locked
dependencies (`litellm==1.83.0`, `openai-agents==0.7.0`) — no API key needed.
Line citations are into `.venv/lib/python3.12/site-packages` at those versions
and will drift if either is bumped.

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

**b) `$defs`/`$ref` reach Anthropic unresolved.** All five real output types emit
them, because `ensure_strict_json_schema` (`agents/agent_output.py:113`) applies
strict rules *through* refs without inlining them. LiteLLM's *native* path
deep-copies and calls `unpack_defs` (`transformation.py:805`, `:811`) with an
explicit comment that Anthropic does not support external schema references — the
emulation path does a bare `_input_schema.update(json_schema)` (`:1109`) and
unpacks nothing.

Our `ReasoningBlock[T]` generics are the main source of refs, but note the plain
models emit them too, so this is not a generics-only problem.

Three ways out, roughly in order of appeal:

1. Get the model onto the native path. Confirm whether a newer LiteLLM has
   `sonnet-5` in the allowlist; if so, bump and pin. This fixes both defects at
   once and is the only option that needs no code in this repo.
2. Enable thinking. Per `:1017`, no `tool_choice` is set when thinking is enabled,
   so the model is merely nudged toward the output tool and can still call real
   tools. Non-deterministic, and does not address the refs.
3. Stop using `output_type` on the tool-using agents and parse a final message
   instead. Largest change, but provider-independent.

`claude-fable-5-1` additionally rejects forced `tool_choice` outright, so it cannot
be `EXTRACTION_MODEL` on the emulation path at all. Worth rejecting that
combination in `Env` validation rather than discovering it in production.

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

1. Does Anthropic accept the SDK's strict-schema dialect, specifically `$ref`/`$defs`
   inside a tool `input_schema`? One small call. Determines whether Blocker 1b is
   fatal or theoretical.
2. Does `claude-fable-5-1` actually 400 on forced `tool_choice`? One call.
3. Does `cache_control_injection_points` via `extra_args` produce nonzero
   `cache_read_input_tokens`, and does the default TTL survive our task gaps? Two
   calls plus a gap.
4. Fable 5.1 vs Sonnet 5 quality on pedigree and table images. Needs a real eval
   set, not a spike.

Note LiteLLM authenticates with a raw `x-api-key`; an `ant auth login` OAuth
profile will not be picked up. This needs an actual `ANTHROPIC_API_KEY`.

## Suggested order

1. Merge PR #137. CI is green, no conflicts; it needs an approving review.
2. Pin an upper bound on `litellm`.
3. Flip `VLM_MODEL` to Anthropic behind the retention check — real signal, and it
   depends on none of the blockers.
4. Resolve Blocker 1 — this is the go/no-go for `EXTRACTION_MODEL`, and option 1
   (get onto the native path) may make it a version bump rather than a code change.
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
