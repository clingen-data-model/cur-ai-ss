# Anthropic migration: what's left after LiteLLM routing

Status as of 2026-09-09, written against the `litellm-model-routing` branch (PR #137).

## Where we are

PR #137 builds a seam, not a migration. `lib/agents/model_factory.resolve_model()`
turns a `<provider>/<model>` name into either a bare string (OpenAI, served by the
SDK's default provider) or a `LitellmModel`. All 17 agents take
`model=extraction_model()`; both VLM tools go through `lib/agents/vision.vlm_describe()`.
Defaults still name OpenAI models, so behavior is unchanged.

The `openai/` special case in `resolve_model()` exists for exactly one reason:
`LitellmModel` ignores `conversation_id`, and the additional-context rerun flow
depends on it. That is the blocker the PR names. Two more are not in the PR
description and are described below.

## Blocker 1: `conversation_id` → sessions

`lib/tasks/handlers.py` repeats the same six-step dance in ~12 handlers: read
`task.conversation_id`, call `ensure_conversation_id()`, branch on
`additional_context`, `Runner.run(..., conversation_id=...)`, persist the id back
on the task. That loop is the whole blocker.

Sessions and `conversation_id` are **mutually exclusive within a single run** — the
agents SDK rejects combining them. So this is a swap, not a layering, which
suggests two independently verifiable steps rather than one:

1. Replace `conversation_id=X` with `session=OpenAIConversationsSession(...)`.
   Behavior-identical, still OpenAI-server-side, but it proves the seam and
   collapses the 12 copies into one helper.
2. Swap the implementation for `SQLAlchemySession`, which runs on the engine this
   project already has.

### Storage decision worth making up front

`SQLAlchemySession` persists full transcripts. With the paper markdown in every
initial message and roughly 40 agent runs per paper (several task types are
per-patient or per-family), that table grows fast.

But turn 0 is deterministically reconstructible — it is
`format_paper_context(fulltext_md(paper_id, supplement_format), gene_symbol)` plus
the agent's instructions, all of which are already in the database. A custom
session that stores only assistant outputs and follow-up turns, rebuilding turn 0
on demand, would be far lighter.

The tradeoff: we lose the intermediate tool-call transcript that the OpenAI
Conversations API currently replays on reruns. For a follow-up prompt that asks the
model to revisit its own conclusion, replaying `[initial message, final output,
follow-up]` is probably sufficient — but that is a judgment call, not a given.

## Blocker 2: prompt caching (highest cost risk)

OpenAI caches automatically. Anthropic requires explicit `cache_control`
breakpoints — max 4 per request, 5-minute default TTL, 1 hour available.

This pipeline is more caching-dependent than it looks. HPO linking runs
`max_turns=15` and MONDO linking `max_turns=25`, and **every one of those turns
re-sends the full paper markdown**. Flip `EXTRACTION_MODEL` to Anthropic without
addressing this and the hit rate silently drops to zero: identical outputs,
several times the bill, no error anywhere.

The instrument that would catch it goes quiet at the same moment.
`log_cache_metrics` reads `usage.input_tokens_details.cached_tokens`; Anthropic
reports `cache_read_input_tokens`. PR #137 made that function *tolerant* of the
missing field, which is correct for not crashing, but it means an Anthropic run
reports a confident `0.0%` whether or not caching is working.

**Fix the metric before the flip, not after.** It is the instrument we would use to
detect the problem.

Open question needing a spike: where a `cache_control` breakpoint gets injected
when `LitellmModel` builds the message list. Probably via `ModelSettings` extra
args or a LiteLLM-level setting — unverified.

## Blocker 3: structured-output conformance (the PR's Step 0, narrowed)

The PR frames this as conformance "for the generic output types." Most of the 16
output types are plain models and are low risk. Worth narrowing the spike to:

- `ReasoningBlock[MondoAgentDecision]`, `ReasoningBlock[HPOTerm]`,
  `ReasoningBlock[HarmonizedVariant]` — generics produce `$defs`/`$ref` in the
  emitted JSON schema.
- `output_type=list[ExtractedPhenotype]` in `patient_phenotype_linking_agent` — a
  root-level array rather than an object.
- The 8 agents that combine `output_type` **with real function tools**. On
  Anthropic a schema-constrained output typically becomes a forced tool call,
  which competes with the search tools the agent is meant to call first. That
  combination is the actual risk, not the schemas in isolation.

### Guardrail worth adding

`claude-fable-5-1` rejects forced `tool_choice` with a 400. That is harmless for
`VLM_MODEL` (`vlm_describe` sends no tools) but would break the same model as
`EXTRACTION_MODEL` if structured output routes through a forced tool. Worth
rejecting that combination in config validation so nobody discovers it in
production.

## The VLM path is already migratable

`vlm_describe` calls `litellm.completion` directly — no `conversation_id`, no
structured output, no tools. It is the one seam in PR #137 that touches none of
the three blockers.

Flipping `VLM_MODEL` to an Anthropic model is a one-line env change that buys real
production signal — auth, latency, refusal handling, billing shape — while the
sessions work proceeds in parallel.

Two things to confirm first, because either could invalidate the target before any
code is written:

- **Data retention.** `claude-fable-5-1` requires 30-day retention and is not
  available under zero data retention without Anthropic's express authorization.
  Worth confirming our org's posture now.
- **Cost.** Fable 5.1 is $10/$50 per MTok against Sonnet 5 at $2/$10. For "describe
  this pedigree" and "extract this table", worth checking whether Sonnet 5 clears
  the accuracy bar before committing to the premium tier.

## Observability regression to close

PR #137 disables tracing (`lib/core/agents_init.py`) and drops both
`RunConfig(trace_metadata)` blocks — `paper_id`, `phenotype_id`, `concept`,
`disease_text`, `gene_symbol`. Disabling tracing is the right call, since the SDK
uploads to OpenAI by default and models may now route elsewhere.

But it removes run-level observability immediately before the migration where we
would most want to compare runs across providers. Structured logging off
`result.raw_responses` would fill the gap locally and cheaply.

## Suggested order

1. Merge PR #137. CI is green and there are no conflicts; it needs an approving
   review.
2. Flip `VLM_MODEL` to Anthropic, behind the retention check. Real signal, near-zero
   risk.
3. Fix `log_cache_metrics` for the Anthropic usage shape. The instrument has to
   work before the thing it measures.
4. Sessions refactor, in the two steps above.
5. Caching spike and structured-output spike. These are the real go/no-go for
   `EXTRACTION_MODEL`.
