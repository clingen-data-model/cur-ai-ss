# Anthropic migration: what's left after LiteLLM routing

Status as of 2026-09-14. Originally written against the `litellm-model-routing`
branch (PR #137). That PR was split: #138 landed the model-name seam, base64
vision images and the VLM failure handling, and PR A landed the `litellm` pin
and the routing branch. #137 itself is closed. Sections below are marked where
the work has since landed.

## How to read this document

Claims here fall into three tiers, and the difference matters:

- **Executed** — code was run locally against the locked dependencies
  (`litellm==1.100.0`, `openai==2.20.0`, `openai-agents==0.7.0`, Python 3.12.14)
  and the output is quoted. Trustworthy. Where a finding predates the litellm bump
  it says so.
- **Source-read** — a dependency's source was read but not run. High confidence,
  not proof.
- **Documented** — taken from Anthropic's docs. Describes what the provider
  *should* do; we have not observed it.

**Nothing in this migration has made an API call to any provider.** There is no
`ANTHROPIC_API_KEY` and no `OPENAI_API_KEY` in this environment; `.env.test`
carries a fake one. The app has never been started against a real model and no
paper has been processed. So the **request-construction** layer is empirically
verified and the **provider-response** layer is not verified at all. Line
citations point into `.venv/lib/python3.12/site-packages` and will drift on a bump.

## Where we are

**Landed.** `lib/agents/model_factory.resolve_model()` turns a `<provider>/<model>`
name into either a bare string (OpenAI, served by the SDK's default provider) or a
`LitellmModel`. All 19 agents take `model=extraction_model()`; both VLM tools go
through `lib/agents/vision.vlm_describe()`, which calls `litellm.completion`.
Defaults still name OpenAI models, so behavior is unchanged.

`ROUTABLE_PROVIDERS` is `{'openai', 'anthropic'}` and the settings validator
requires each configured model's provider key, so **`VLM_MODEL=anthropic/...` works
today**. **2026-09-22: the observability gap is now closed** — `set_tracing_disabled(True)`
runs at both process entrypoints (`lib/core/agents_init.py`) and the three
`RunConfig(trace_metadata=...)` blocks were replaced by `log_run_metrics` calls — see
*Observability gap* and *Suggested order* below. `EXTRACTION_MODEL` flipping to
Anthropic is therefore unblocked from this side; the flip itself is a separate,
not-yet-made decision.

The `openai/` special case still exists, but no longer because `LitellmModel`
ignores `conversation_id` — **source-read**: literally annotated
`conversation_id: str | None = None,  # unused` at `litellm_model.py:161` and
`:271`, never referenced in either body, and nothing in the pipeline passes that
parameter anymore. It is kept as a deliberate, undone decision — see Blocker 2,
"`openai/` no longer needs to bypass LiteLLM — but still does."

## Blocker 1: structured output — fixed by bumping LiteLLM

This was the top risk. It is a LiteLLM defect, not an Anthropic limitation or a
problem with our models, and a version bump resolves it.

Under 1.83.0, which this branch started on, the native-vs-emulated decision is a hardcoded set of
model-name substrings (`llms/anthropic/chat/transformation.py:988`-`:1005`) that
`claude-sonnet-5`, `claude-opus-5` and `claude-fable-5-1` all miss. **Executed**,
against the real agents' real output types:

```
# litellm 1.83.0
tool_choice: {"name": "json_tool_call", "type": "tool"}
tools sent : ['json_tool_call', 'search_hpo_terms']
has $ref   : True
```

A forced `tool_choice` alongside the real tools means the model must emit the JSON
tool immediately and can never reach `search_hpo_terms`. No error is raised — the
task succeeds with structured output derived from zero ontology lookups. HPO
linking has 4 tools and `max_turns=15`; MONDO 9 tools and 25; harmonization 7.

LiteLLM `main` has since replaced that substring set with a capability lookup
(`_supports_model_capability(model, "supports_native_structured_output", ...)`) and
guarded the forced `tool_choice` behind `AnthropicModelInfo.forced_tool_use_unsupported(model)`.
**Executed** under 1.100.0 via an ephemeral overlay:

```
claude-sonnet-5    native=True  tool_choice=null  tools=['search_hpo_terms']
claude-opus-5      native=True  tool_choice=null  tools=['search_hpo_terms']
claude-fable-5-1   native=True  tool_choice=null  tools=['search_hpo_terms']
claude-sonnet-4-6  native=True  tool_choice=null  tools=['search_hpo_terms']
```

Native path, no forced tool choice, only the real tool. That also removes the
separate `claude-fable-5-1` concern: `forced_tool_use_unsupported` means no forced
`tool_choice` is ever set for it, so it cannot 400 on one.

**Landed**, pinned at `litellm==1.100.0`. The result above was re-confirmed
against the locked resolution rather than the overlay, and again on the merged
pin (`claude-sonnet-5`, `claude-opus-5`, `claude-fable-5-1` all `native=True`,
`tool_choice=null`, real tool only). The full suite passes at 196. See
*Dependency versions* for the cascade it forced.

### Our schemas were never the problem

**Executed** — a scan across 13 agents found every output schema clean: no
`minimum`, `maximum`, `multipleOf`, `minLength`, `maxLength`, `pattern`,
`maxItems`, `uniqueItems`, no `minItems` outside 0/1, and no external `$ref`.

`$defs`/`$ref` are present in all of them (`ensure_strict_json_schema` at
`agents/agent_output.py:113` applies strict rules *through* refs without inlining
them), but **documented**: internal refs are supported and only external
(`http://...`) refs are not. No Pydantic model in this repo needs to change.

Also **documented**, and relevant either way: structured outputs and tool use
compose in one request — Claude either calls a tool (`stop_reason: "tool_use"`) or
returns structured JSON (`end_turn`), deciding per turn. The current parameter is
`output_config.format`; LiteLLM's native branch still emits the deprecated
`output_format`, accepted during a transition period.

## Blocker 2: `conversation_id` → sessions

**Landed 2026-09-14** (`lib/tasks/agent_session.py`, migration
`99bb61eac734_drop_tasks_conversation_id_column.py`). At the time this was
written it looked like the last blocker to an `EXTRACTION_MODEL` flip — it
wasn't; see Blocker 4, found the next day by actually trying the flip.

What actually shipped differs from the plan below in two ways, both direct
decisions rather than discoveries mid-implementation:

- **Skipped the `OpenAIConversationsSession` intermediate step.** The plan's
  two-step swap (below) was written to keep the change behavior-preserving on
  already-persisted ids. We went straight to `SQLiteSession` instead, so
  every previously-stored `conversation_id` became unreachable in one step —
  the same "accept the data loss, document it" call already made for the
  chat feature. `tasks.conversation_id` is dropped outright, not migrated.
- **No empty-session detection in the `additional_context` branch.** The
  concern below (a fresh session is empty, so a follow-up sent into one would
  have no paper attached) turns out to describe a pre-existing gap, not a new
  one: the *old* code had the identical failure mode any time `additional_context`
  was set on a task's first-ever run — `ensure_conversation_id(None)` minted a
  fresh, equally empty OpenAI conversation. `agent_session(task_id)` is
  deterministic on the task's id rather than round-tripped through a mint
  call, but a task row created with `additional_context` already set (never
  run before) still hits an empty session either way. Not fixed here, because
  it is not a regression — the "Rerun Agent" UI only offers a context field on
  a task that has already produced output once.

Each of the ~14 handlers in `lib/tasks/handlers.py` used to repeat the same
six-step dance: read `task.conversation_id`, `ensure_conversation_id()`,
branch on `additional_context`, `Runner.run(..., conversation_id=...)`,
persist the id back. 58 references in that file alone, now zero — replaced by
`agent_sess = agent_session(task_id)` and `Runner.run(..., session=agent_sess)`,
with `await agent_sess.clear_session()` on the branch that starts fresh.

**One of the two Responses-API-direct call sites this section used to list is
already gone.** The chat feature (`chat_routing_agent`, `general_paper_qa_agent`,
the paper-level `ConversationDB`, all four `/papers/{id}/chat/*` endpoints, the
Streamlit tab) was a proof of concept ahead of a real streaming rebuild in the
React SPA, and was deleted outright on 2026-09-14 rather than carried through this
refactor -- see its migration, `4993494a8281_drop_the_chat_feature.py`. That
removed the chat follow-up turn in `lib/api/app.py`, and with it
`model_factory.responses_api_model()`'s only caller, so the function is deleted
too rather than waiting for this refactor to do it. `ensure_conversation_id` in
`handlers.py` served the unrelated per-task `additional_context` follow-up
feature ("Rerun Agent" with extra context, in both UIs) -- which is what this
refactor was about -- and is now deleted along with it.

Sessions and `conversation_id` are mutually exclusive within a run, so this was a
swap, not a layering. The plan below called for two independently verifiable
steps — an intermediate `OpenAIConversationsSession` before the local one — but
as noted above, we went straight to step 2:

1. ~~Replace `conversation_id=X` with `session=OpenAIConversationsSession(conversation_id=X)`.~~
   **Skipped** — see the "Landed" note above.
2. Swap the implementation for a local session. **Done**, with `SQLiteSession`.

**The `openai-agents` bump does not help here.** **Source-read** at the released
`v0.22.2` tag: `LitellmModel`'s `conversation_id` is *still* annotated `# unused`
(`litellm_model.py:219` and `:392`). An earlier revision of this doc guessed it
might have been implemented across fifteen minor versions. It has not. The sessions
refactor was genuinely required, and it did not need the bump either.

### Use `SQLiteSession`, not `SQLAlchemySession`

`SQLiteSession` ships in the **locked 0.7.0** (`agents/memory/sqlite_session.py:21`):

```python
SQLiteSession(session_id, db_path=':memory:',
              sessions_table='agent_sessions', messages_table='agent_messages')
```

A plain filesystem path — no `AsyncEngine`, no async driver, no second engine, and
portable across platforms. That is the deciding factor.

`SQLAlchemySession` is the wrong tool here: **source-read**, in both 0.7.0
(`agents/extensions/memory/sqlalchemy_session.py:59`) and 0.22.2 (`:146`) it still
requires `engine: AsyncEngine`, so it would force an `aiosqlite` dependency and a
second async engine alongside the sync one in `lib/api/db.py`.

**Point `db_path` at its own file** — landed at `{CAA_ROOT}/sqllite/agent_sessions.db`
(`lib/tasks/agent_session.py`) — rather than the app database. The SDK creates and
owns `agent_sessions` / `agent_messages` itself, and tables outside Alembic's model
metadata sitting in `app.db` invite `alembic revision --autogenerate` proposing to
drop them. A separate file keeps the SDK's schema and ours from fighting, and
sidesteps the `ondelete="CASCADE"` hazard in `CLAUDE.md` entirely.

### The `additional_context` branch: both concerns resolved, differently than planned

This was flagged as not a pure swap, and the part most likely to bite. Handlers
branch: when `additional_context` is set they send *only* the follow-up prompt and
relied on OpenAI's server-side history to supply the paper. A freshly created
client-side session is **empty**, so that branch would send a bare "Please review
your previous analysis in light of..." with no paper attached.

Two things were flagged; see the "Landed" note at the top of this section for why
neither was implemented as originally planned:

1. Seeding or detecting an empty session was **not implemented** — turned out to
   describe a pre-existing gap in the old code too, not something this change
   introduces.
2. **Every `conversation_id` already persisted became unreachable** — resolved by
   deciding, not defaulting: the migration drops the column outright rather than
   keeping a legacy read path, the same choice already made for the chat feature's
   conversation history.

### Storage design worth deciding first

`SQLiteSession` persists whatever the run produced, verbatim. With the paper
markdown in every initial message and roughly 40 agent runs per paper, that file
grows fast — and the same reconstructibility that solves the empty-session problem
above also means we do not have to store turn 0 at all.

So there is a choice, and it is worth making deliberately rather than by default:

- **Store everything** (plain `SQLiteSession`). Simplest, closest to today's
  behavior, and the session file carries the full tool-call transcript. Costs disk
  roughly linear in papers × agents × paper size.
- **Store only what is not reconstructible** — a thin `Session` implementation
  wrapping `SQLiteSession` that drops turn 0 on write and rebuilds it on read. Much
  smaller, and the `Session` protocol is only four methods (`get_items`,
  `add_items`, `pop_item`, `clear_session`). **But rebuilding must be
  byte-identical** or the prefix hash changes and prompt caching stops working —
  which makes `fulltext_md()` determinism and every agent's instructions constant
  load-bearing for cost. Worse, it fails silently and asymmetrically: edit an
  agent's prompt and every stored session now replays a history the model never
  actually saw. It also loses the intermediate tool-call transcript the
  Conversations API replays today.

**Went with store-everything**, as recommended: `agent_session()` returns a plain
`SQLiteSession`, no wrapping. The thin option's byte-identical-reconstruction
requirement was too fragile a coupling between prompt text and cache correctness
to take on in the same change; measuring whether the session file is actually a
disk problem in practice is still open, not urgent.

### `openai/` no longer needs to bypass LiteLLM — but still does

`model_factory.resolve_model()`'s module docstring now documents this directly
rather than gesturing at a future state: the `openai/` branch existed *only*
because `LitellmModel` ignores `conversation_id` (`litellm_model.py:161`/`:271`),
and the pipeline depended on that parameter. Sessions replaced it, so nothing left
depends on OpenAI's server-side state specifically — `resolve_model()` could route
`openai/` through `LitellmModel` like every other provider, "pseudo-supporting" it
the same way `anthropic/` is supported now rather than privileging it with direct
Responses API access. That would collapse `resolve_model()`'s two branches into
one and remove the last place a provider name changes which code path a request
takes. **Still not done** — left as its own decision rather than a side effect of
this change, since it changes how every OpenAI call is made and deserves its own
testing.

## Blocker 3: prompt caching

**The mechanism works and is one line.** LiteLLM accepts a top-level
`cache_control_injection_points` parameter, and `ModelSettings.extra_args` is
splatted into the `litellm.acompletion` call as top-level kwargs
(`litellm_model.py:475`-`:476`). **Executed** — the hook rewrites the outgoing
messages to carry a real breakpoint (this probe targeted the paper message by role
to prove the mechanism; see below for why the recommended config differs):

```json
{"role": "user",
 "content": "PAPER AND GENE CONTEXT ...",
 "cache_control": {"type": "ephemeral"}}
```

```python
_CONTROL = {'type': 'ephemeral', 'ttl': '1h'}
ModelSettings(extra_args={'cache_control_injection_points': [
    {'location': 'message', 'role': 'system', 'control': _CONTROL},
    {'location': 'message', 'index': -1, 'control': _CONTROL},
]})
```

**This must be gated on the provider.** `extra_args` is not LiteLLM-specific — the
SDK splats it into the OpenAI Responses call too (`models/openai_responses.py:309`
and `:344`, **source-read**). Since `openai/` names deliberately bypass
`LitellmModel` and go to the default provider, attaching these settings
unconditionally would send `cache_control_injection_points` to OpenAI, which does
not know the parameter — plausibly a 400 on every agent call. `model_factory`
already knows the provider via `split_provider`, so that is where the gate belongs.

**Landed 2026-09-14, in `model_factory.model_settings_for()`**, gated on the
provider, and all 17 extraction agents take `model_settings=extraction_model_settings()`.
(A prior revision of this section claimed this under the **Executed** tier with a
quoted `extra_args` dump; that was false — the function did not exist in the tree
at the time. See Corrections log, item 8.)

**Executed for real this time**, with a key, against `paper_section_classifier_agent`
(no tools, single turn — the simplest agent that still exercises the system+message
breakpoint pair) on `anthropic/claude-sonnet-5`, a real ~24K-token paper as the
`PAPER AND GENE CONTEXT` message:

```
call 1 (prefix forced fresh):  cache_creation_input_tokens=24201  cache_read_input_tokens=0
call 2 (identical prefix):     cache_creation_input_tokens=0      cache_read_input_tokens=24201
```

24201 of 24202 prompt tokens read from cache on the second call — a 100% hit, not
merely a nonzero one. `lib.tasks.handlers.log_cache_metrics` (landed in PR #116,
months before this migration — see Corrections log, item 1) reported it correctly
without any change: `[CACHE] CALL 2: input=24202 cached=24201 (100.0%)`. Read cost
came out to ~0.1x write cost per token, matching the documented 2x-write/0.1x-read
economics exactly. This answers *What still needs a live key*, item 3.

One caveat: this was a single isolated call, not the 15-turn HPO loop the
$2.40-vs-$0.54 estimate below is about. The mechanism and the per-token economics
are now verified; the compounding effect across a real multi-turn tool loop is
not, since that needs `EXTRACTION_MODEL` itself on Anthropic (Blocker 2).

**Use `index: -1`, not `role: 'user'`.** Role targeting returns *every* matching
index (`anthropic_cache_control_hook.py:336`) and the cap is
`MAX_CACHE_CONTROL_BLOCKS = 4`, with injection stopping once reached rather than
erroring. On a thread that accumulates follow-ups — paper, follow-up 1, follow-up 2
— the first four user messages get stamped and the **last** one does not, which is
exactly the position the incremental read needs. `index: -1` moves the breakpoint to
the end of each request, which is the documented incremental pattern and what
LiteLLM itself defaults to.

`ttl` goes in that same `control` dict. There is no per-message hook in the agents
SDK — messages are built wholly by the converter — so `extra_args` is the only seam.

Why this should pay off well here (**documented**): the tool loop is exactly
Anthropic's incremental multi-turn pattern — write at the breakpoint, next
request's lookback finds the prior write. HPO's 15 turns and MONDO's 25 re-send the
paper every turn, so everything after turn 1 reads at 0.1x. For one HPO run over an
~80k-token paper on Sonnet 5, that is roughly **$2.40 uncached against ~$0.54
cached** — a 1 write at 2x plus 14 reads at 0.1x.

*(Correction, 2026-09-10: an earlier revision quoted ~$0.42 here. That is the
**5-minute** figure, computed at the 1.25x write multiplier while the section
recommends `ttl: "1h"`, whose write is **2x**. The saving is ~4.4x, not ~5.7x.
Still clearly worth doing; the conclusion is unchanged.)*

**Break-even is three requests, not two.** At 1h the write costs 2x, so the entry
must be read at least twice to beat sending uncached (2x + 0.2x against 3x); at 5m
it is 1.25x and two requests suffice. Tool loops clear three trivially. The
human-review case is what the task-timestamp query below has to decide. Our prompt
is already ordered correctly: `message = f'{paper_context}\n\n{INSTRUCTIONS}'` puts
the stable paper first in a *single* user block, which avoids the documented
headline mistake of putting a breakpoint on content that changes per request.
Sonnet 5's minimum cacheable prefix is 1,024 tokens; a paper is far above it.

Two real limits:

**Cross-agent reuse is structurally impossible.** Prefix order is
`tools → system → messages`. Each agent has different instructions and a different
tool set, so the paper always sits behind a divergent prefix and the cumulative
hash at that block differs per agent. You get one cache entry per *agent run*, not
per paper — and it cannot be fixed by reordering, because `system` always renders
before `messages`. With ~40 runs per paper, that is the ceiling on savings.

**The 5-minute default TTL probably does not fit this pipeline.** It is measured
from the *start* of the writing or reading request, and generation time counts
against it. Fine within one tool loop; risky across tasks. The worker runs
sequentially under a 900s lease, and demographics / phenotype extraction / HPO
linking fan out per patient. If consecutive runs land more than ~5 minutes apart,
every one pays a fresh write at 1.25x and never reads — worse than not caching at
all.

The stronger argument for `ttl: "1h"` is the **human review loop**, not pipeline
gaps. A curator reads an extraction in the UI and asks a follow-up; that reruns the
agent against a session whose prefix is byte-identical to the original run's. Under
a 5-minute TTL that is essentially always a miss plus a fresh write. Under an hour
it plausibly hits, and a hit there is worth much more than one inside a tool loop
because the whole paper is in the replayed prefix.

**Saving the transcript locally does not by itself produce a cache hit** — worth
stating because it is an easy inference to make. Anthropic's cache is server-side
and ephemeral, and a read only finds an entry a *prior request wrote* that has not
expired; it is not content-addressed. A byte-identical prefix sent after the TTL is
a miss, not a hit.

**Decision: use `ttl: "1h"`.**

**One hour is the ceiling — there is no longer option.** Anthropic offers exactly
two TTLs, `5m` (the default) and `1h`. A day-long or indefinite cache is not
something we can opt into, so this is a choice between two values, not a tunable.

The one thing that softens that: **the TTL is measured from the start of the request
that writes *or reads* the entry**, so a read refreshes it (the pricing table calls
it "cache read (hit/refresh)"). The limit is on *idle* time, not total age. A prefix
touched at least hourly stays hot indefinitely — a paper being worked continuously
could hold its cache all afternoon — while a follow-up the next morning is cold
regardless of configuration.

So the measurement question is not "how long do we want" but "what fraction of
extraction→rerun gaps fall under an hour." Task timestamps are already in the
database, so that is a query. If most reruns are next-day, `1h` buys nothing for the
review loop and we would be paying **2x on every write instead of 1.25x** to get it.
The intra-pipeline case is the more reliable payoff: roughly 40 runs per paper very
likely span more than 5 minutes and less than an hour, which is precisely the band
`1h` covers and `5m` misses.

`max_tokens: 0` pre-warming is rejected when structured outputs are on, so the
paper cannot be pre-warmed ahead of a run. **That also closes off the cheaper
alternative to a 1h TTL**: for the 5-60 minute gap, Anthropic's own guidance is
usually to stay on the 5-minute TTL and re-send the prior request with
`max_tokens: 0` before the entry expires — a keep-alive that refreshes the timer
and bills only a cheap read, avoiding the doubled write. Every extraction agent
uses structured outputs, so that option is unavailable to us and `ttl: "1h"` stands
as the right choice — for a more specific reason than the original argument gave.

## Blocker 4: Anthropic's union-type schema limit — fixed for the 4 affected agents

**Discovered and fixed 2026-09-15**, running the real pipeline end-to-end on
`EXTRACTION_MODEL=anthropic/claude-sonnet-5` against a real paper (ITPR3,
"Dominant mutations in ITPR3 cause Charcot-Marie-Tooth disease", 5 affected
patients across two families) — the first real trial of the sessions work from
Blocker 2, and it surfaced a blocker that section didn't anticipate.

**Executed.** `VARIANT_EXTRACTION` and `PATIENT_EXTRACTION` failed on every one
of 3 automatic retries with a 400 from Anthropic:

```
Schemas contains too many parameters with union types (61 parameters with type
arrays or anyOf). This causes exponential compilation cost. Reduce the number
of nullable or union-typed parameters (limit: 16 parameters with unions).
```

(61 for `VariantExtractionOutput`; `PatientExtractionOutput` hit the same wall
at 18.)

**Root cause: EvidenceBlock reuse, dereferenced.** Every extracted field is
wrapped in `EvidenceBlock[T]` (`lib/models/evidence_block.py`) — `value: T`,
plus `quote`/`table_id`/`image_id`, all independently nullable. Pydantic emits
that wrapper once as a shared `$defs` entry no matter how many fields reuse it,
so the schema *as generated* is compact. Anthropic's schema compiler doesn't
see it that way: it has to fully dereference every `$ref` to build its decoding
grammar (external refs aren't supported, and even the client-side inlining
LiteLLM does for Anthropic — `litellm/llms/anthropic/chat/transformation.py`'s
`unpack_defs`, **source-read** — wouldn't matter, since Anthropic's own
compiler has to expand internal refs regardless of what's sent over the wire).
Sixteen genuinely-optional concepts read as sixteen; the same wrapper reused 15
times reads as 61.

**Not a stale-model artifact.** A similar-shaped issue reported against an
unrelated project claimed current-generation Claude models don't hit this limit
at all — only older ones forced through a legacy tool-schema compiler.
Checked and ruled out as the explanation here: **source-read**,
`AnthropicModelInfo._supports_model_capability('anthropic/claude-sonnet-5',
'supports_native_structured_output', 'anthropic')` returns `True` in the locked
LiteLLM, confirming our calls already use Anthropic's newer native
`output_format` path, not the legacy forced-tool-call path — and it fails
there too. Trust our own live, reproducible result over a secondhand report.

**Census: 4 of 17 agents are over the limit, not 2.** Generating each agent's
`output_type` schema, dereferencing `$ref`s the same way, and counting
`anyOf`/nullable nodes (script output matched the two live failures exactly —
61 and 18 — confirming the methodology):

| Agent | Union count | Anthropic-safe? |
|---|---|---|
| `variant_extraction_agent` | 61 | no |
| `patient_demographics_agent` | 40 | no (never reached in the first live run — patient extraction failed before its successor could queue) |
| `patient_variant_occurrence_agent` | 20 | no (also never reached) |
| `patient_extraction_agent` | 18 | no |
| `mondo_linking_agent` | 11 | yes |
| `paper_extraction_agent` / `patient_phenotype_linking_agent` / `segregation_evidence_extractor` | 7 | yes |
| `variant_harmonization_agent` | 6 | yes |
| `hpo_linking_agent` / `pedigree_describer_agent` | 2 | yes |
| `table_correction_agent` | 1 | yes |
| `compound_het_agent` / `paper_section_classifier_agent` / `segregation_analysis_computed_agent` | 0 | yes |

The pattern is structural, not incidental: every agent dense with
`EvidenceBlock`-wrapped fields is over the limit; every other agent clears it
comfortably.

**Rejected: branching on provider.** The obvious-looking fix — native
structured output on `openai/`, something else on `anthropic/` — was rejected
outright. It's the same class of special-casing this whole migration has been
undoing (see Blocker 2's "openai/ no longer needs to bypass LiteLLM"): a
schema too complex for Anthropic's compiler is a fact about the *agent's
schema*, not about which provider happens to be configured today, and OpenAI
gains nothing from a code path Anthropic can't also use.

**Fix: `output_type=None` on the 4 over-limit agents, unconditionally.**
`lib/agents/manual_output.py` — `AgentOutputSchema.is_plain_text()` is a
first-class SDK mode (**source-read**, `agents/agent_output.py:127-129`): when
`output_type` is `None`, no schema reaches the provider at all, on any
backend, and `result.final_output` is the model's raw text. The four agents'
own `output_type` is now permanently `None`; `run_with_manual_output()` embeds
the target Pydantic model's JSON schema in the prompt as documentation (never
sent to the API for enforcement), then validates the response client-side with
`model_validate_json()`, repairing in the same session — the model sees its
own invalid output plus what was wrong with it — up to 3 attempts before
failing the task (which still has the worker's own outer retry as a backstop).

**Reliability — checked against real-world reports before trusting it.**
Practitioner writeups on Claude structured-output patterns (not this
project's data) put pure prompt-only JSON at ~85% single-shot reliable and
explicitly discourage it for production; a stronger "assistant prefill"
pattern (seed the reply with `{`) reports ~90% but "struggles with deeply
nested structures" — which describes these schemas exactly. We did not
implement prefill (the agents SDK's `input` is the next turn, not a partial
assistant continuation, and wiring it through would mean bypassing the SDK the
way `vision.py` already bypasses it for VLM calls) because the empirical
result below didn't show a need to.

**Executed, on the real paper**: all 4 previously-failing calls succeeded on
the **first attempt** — `VARIANT_EXTRACTION`, `PATIENT_EXTRACTION`, all 6
per-patient `PATIENT_DEMOGRAPHICS` calls, and `PATIENT_VARIANT_OCCURRENCES` —
zero repair-loop warnings logged across 8 calls. Final extraction: 6 patients,
2 probands, 4 variants, 5 patient-variant links. Small sample — 8 calls is not
a production reliability estimate — so this is worth watching once
`EXTRACTION_MODEL` actually flips for real traffic, not a closed question.

## Corrections log

Nine claims in earlier revisions of this document were wrong. Recorded so the
reasoning is auditable — and note that three of the nine clustered on the same
subject, LiteLLM's structured-output routing, which is a signal about where the
guessing was happening.

1. **`log_cache_metrics` needs fixing.** Retracted. `litellm_model.py:212`-`:214`
   translates litellm's `prompt_tokens_details.cached_tokens` into the SDK's
   `input_tokens_details.cached_tokens` — exactly what the function already reads —
   and litellm's `prompt_tokens` already includes cached tokens, so the denominator
   is right too. (Raw Anthropic `input_tokens` *excludes* cached tokens, which is
   where the confusion came from; litellm normalizes to OpenAI semantics.)
2. **Unresolved `$defs`/`$ref` would be rejected.** Retracted. Internal refs are
   supported; only external ones are not. LiteLLM's `unpack_defs` comment refers to
   the external case.
3. **"There is no LiteLLM version to upgrade to."** Retracted, and it was the
   costliest error — it argued for a local shim and an upstream PR when a bump
   suffices. It came from a grep for `sonnet-5` returning nothing on `main`; the
   control term `sonnet-4.6` also returned nothing, which should have revealed
   immediately that the mechanism had been refactored rather than left stale.
4. **"The `litellm` bump is surgical and should not be bundled with the `openai`
   bump."** Retracted. It cannot be unbundled: 1.100.0 requires
   `openai>=2.20.0` and `pydantic-settings>=2.14.1`, so three pins move together
   or none do. The claim was made without attempting the resolution.
5. **"The `openai-agents` bump may moot Blocker 2."** Retracted. `conversation_id`
   is still annotated `# unused` on `LitellmModel` at the released `v0.22.2` tag.
   This was a guess about fifteen versions of changelog, offered as a reason to
   defer the sessions work; checking took one HTTP request.
6. **The cached-vs-uncached figure for an HPO run.** Corrected 2026-09-10. The
   quoted ~$0.42 was computed at the 5-minute write multiplier (1.25x) in a section
   recommending the 1-hour TTL (2x). The right figure is ~$0.54 against $2.40. The
   error flattered the recommendation being made; it does not change it.
7. **The `VLM_MODEL` cost comparison omitted Opus 5.** Corrected 2026-09-10. It
   presented Fable 5.1 ($10/$50) against Sonnet 5 ($2/$10) as the only choice, when
   Opus 5 sits between them at $5/$25 and carries none of Fable 5.1's retention
   constraint.
8. **"Wired in `model_factory.model_settings_for()`... Executed against real
   agents under both providers," with a quoted `extra_args` dump.** Retracted
   2026-09-14 — the costliest error in this document, because it used the
   **Executed** tier, the one this doc asks readers to trust. `model_settings_for`
   did not exist anywhere in `lib/` when that was written; grepping for it (or for
   `extraction_model_settings`) on `main` returned nothing. The design underneath
   the claim — the two-breakpoint placement, `index: -1` over role targeting, the
   `ttl: "1h"` choice — was sound and is what actually got built; only the "this is
   already in the tree, and I ran it" part was fabricated. Now genuinely landed and
   executed; see Blocker 3.
9. **"This was the last blocker to an `EXTRACTION_MODEL` flip"** (Blocker 2,
   2026-09-14). Corrected the next day: actually attempting the flip surfaced
   Blocker 4, a schema-complexity limit affecting 4 agents that no prior
   section had checked for. The lesson repeats one already in this log —
   "no live key" claims and "should work now" claims are different tiers, and
   this document kept writing the former in the voice of the latter.

## The VLM path

Still the best first move: `vlm_describe` calls `litellm.completion` directly — no
`conversation_id`, no structured output, no tools — so it touches none of the
blockers and `VLM_MODEL` is a one-line env change.

Images now go as base64 data URLs rather than signed GCS URLs, which removed
`google-cloud-storage`, ADC credentials, the bucket, and a 12-hour URL expiry that
could lapse before a retry. **Documented**: a data URL is the form LiteLLM's
Anthropic provider documents, and an HTTPS URL would also have worked (LiteLLM maps
it to Anthropic's native `source.type: "url"`). `detail: 'high'` is ignored on
Anthropic and still meaningful on OpenAI, so it is harmless.

### Fixed: truncation was treated as success

`vlm_describe`'s original guard was
`finish_reason not in (None, 'stop', 'length', 'end_turn')`, and litellm's
`_FINISH_REASON_MAP` maps Anthropic `max_tokens` → `'length'` — which sat in the
*allowed* list. **Executed** against the original code:

```
normal completion  finish_reason=stop           -> returned content: 'complete table'
TRUNCATED          finish_reason=length         -> returned content: '| A | B |\n| 1 |'
Anthropic refusal  finish_reason=content_filter -> declined (None)
```

So a cut-off response came back as valid content, and for
`extract_table_from_image` that meant a truncated markdown table indistinguishable
from a complete extraction. Truncation is now a decline, logged separately from a
refusal. `'end_turn'` is gone from the accepted set — litellm normalizes it to
`'stop'`, so the branch was dead. The refusal path was already correct.

`max_tokens` is now bounded at 16384. **Executed**:
`get_max_tokens_for_model('claude-sonnet-5')` returns `128000`, not the 4096 the
LiteLLM docs claim — so the risk was never truncation at 4096 but a 128k ceiling on
a non-streaming call inviting HTTP timeouts.

This module previously had no tests; it now covers all four `finish_reason` paths
plus the `max_tokens` bound.

### Before flipping `VLM_MODEL`

- **Data retention.** `claude-fable-5-1` requires 30-day retention and is not
  available under zero data retention without Anthropic's express authorization.
- **Cost, across three tiers — not two.** An earlier revision framed this as Fable
  5.1 against Sonnet 5 and omitted the middle option:

  | model | $/MTok in | $/MTok out |
  |---|---|---|
  | `claude-sonnet-5` | $2 | $10 |
  | `claude-opus-5` | $5 | $25 |
  | `claude-fable-5-1` | $10 | $50 |

  Try Sonnet 5 first and Opus 5 before reaching for Fable 5.1; the retention
  constraint above applies only to Fable 5.1, so the two cheaper options also avoid
  that question entirely.

## Dependency versions

| package | pinned | latest | note |
|---|---|---|---|
| `litellm` | `==1.100.0` | 1.100.0 | bumped on this branch |
| `openai` | `==2.20.0` | 3.11.0 | dragged up by litellm; 2.x only |
| `openai-agents` | `==0.7.0` | 0.22.2 | still behind |
| `pydantic-settings` | `==2.14.1` | — | dragged up by litellm |

**The `litellm` bump was not surgical, contrary to an earlier revision here.**
1.100.0 requires `pydantic-settings>=2.14.1` and `openai>=2.20.0`, so three pins
moved together and there was no way to isolate them. `openai` went to 2.20.0 —
litellm's minimum — rather than the newest 2.x, to keep the change attributable;
litellm caps it below 3.0.0 regardless.

The transitive install weight is larger than an earlier revision listed. Measured
on the merged resolution: **21 packages added, 5 replaced** — `boto3`/`botocore`/
`s3transfer`/`jmespath`, the `aiohttp` stack (`aiohappyeyeballs`, `aiosignal`,
`frozenlist`, `multidict`, `propcache`, `yarl`), `tiktoken`, `fastuuid`,
`importlib-metadata`/`zipp`. Two indirect pins also moved that the earlier list did
not mention: **`httpx` 0.27.0 → 0.28.1** and `jinja2` 3.1.4 → 3.1.6.

`litellm` is now pinned exactly rather than floating, matching its neighbours. The
behavior that decides native-vs-emulated structured output is undocumented and
version-specific, and an unbounded pin can silently move every agent between the
two paths in either direction — which is exactly how this branch came to be broken.

`openai-agents` is still fifteen minor versions behind and is the library the whole
of `lib/tasks/handlers.py` is built on. It wants its own change with the test suite
as the gate — and per Blocker 2, it buys nothing for the sessions work, so there is
no urgency.

## Observability gap

**Landed 2026-09-22.** `lib/core/agents_init.py` (recreated — this is the piece of
#137 that didn't survive the split into #138/PR A/the routing branch) exposes
`init_agents_sdk()`, which calls `set_tracing_disabled(True)`. It runs once at each
process entrypoint that can call `Runner.run` — `lib/api/app.py`'s `lifespan()` and
`lib/bin/worker.py` at module level — right alongside the existing `setup_logging()`
call at each. This is unconditional (no env-var gate): there's no legitimate case for
re-enabling OpenAI-hosted tracing of paper/patient content.

All three `RunConfig(trace_metadata=...)` blocks (HPO linking and MONDO linking in
`lib/tasks/handlers.py`, plus the chat handler in `lib/api/app.py` — this third site
was not in this section's original inventory, since the chat feature was rebuilt in
the React SPA after this doc's "deleted outright" note below) were removed and their
metadata folded into `log_run_metrics` (renamed from `log_cache_metrics`) instead of
just dropped, per this section's original suggestion.

**Verified 2026-09-14** (`agents==0.7.0` source), and the reason this needed fixing:
`RunConfig.tracing_disabled` defaults to `False`, and `trace_include_sensitive_data`
defaults to `True` unless `OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA` is set — it
was set nowhere in `lib/core/environment.py` or the deployed `.env` template. So
before the 2026-09-22 fix above, every `Runner.run` call exported a trace to
OpenAI's backend, tagged with the metadata above, carrying full inputs/outputs.
That was not a new problem and not, at the time, a cross-provider one:
`EXTRACTION_MODEL` was still 100% OpenAI, so an OpenAI-run trace going to OpenAI
was self-consistent with wherever the org already drew the line for that data. It
would have become a cross-provider one the moment `EXTRACTION_MODEL` pointed at
Anthropic (Blocker 2) — the agent runs on Claude, but the same paper/patient
content would still export to OpenAI's tracing dashboard by default, regardless of
which provider actually served the request. That is exactly the risk the
2026-09-22 fix closes.

The `VLM_MODEL` flip (#182, now on `main`) never triggered this: `vlm_describe`
calls `litellm.completion` directly, never `Runner.run`, so vision was never
inside the SDK's tracing scope on either provider.

`lib.tasks.handlers.log_run_metrics` (renamed 2026-09-22 from `log_cache_metrics`,
PR #116, months before this migration began) is the structured-logging replacement
this section used to say was still needed — see Corrections log, item 1, and
Blocker 3 for it working correctly against a live Anthropic response.

**Landed 2026-09-22 alongside the fix above:** `log_run_metrics` now also warns
(`[ZERO_TOOL_CALLS]`) when a tool-using agent completes without calling any tool —
the signature of Blocker 1 recurring after a dependency bump.

## Local environment

Verified working, and the README's prerequisites are now accurate (the `make ci` /
`make test` references were removed — there is no Makefile):

```bash
uv sync && uv pip install -e .        # Python 3.12.14
ENV_FILE=.env.test uv run pytest test -q
```

**Executed**: 196 passed as of PR A (184 on `main` after #138). ruff, format and
mypy clean; `uv sync --locked` consistent.

One wrinkle: `uv run` re-syncs from the lockfile and undoes `uv pip install -e .`,
so the README's two-step is partly self-defeating.

## What still needs a live key

1. **End-to-end on OpenAI first.** This needs only an `OPENAI_API_KEY` and no
   Anthropic involvement, and it would exercise the real pipeline plus the base64
   image change — which currently has no end-to-end coverage for *either* provider.
   The README has a ready case (MASP1, PMID 26419238). Do this before any switch,
   to establish a known-good reference.
2. ~~Does the native structured-output path work end-to-end on Anthropic —
   schema accepted, tool loop still running, SDK parsing the result?~~
   **Answered 2026-09-15: mostly yes, with one real blocker — see Blocker 4.**
   13 of 17 agents' schemas are accepted as-is; the 4 that dereference over
   Anthropic's 16-union-node limit now run through manual JSON output instead
   and were verified end-to-end against a live paper on `claude-sonnet-5`
   (8/8 calls succeeded first attempt, zero repairs needed). The go/no-go for
   `EXTRACTION_MODEL` is otherwise clear.
3. ~~Does `cache_control_injection_points` produce nonzero `cache_read_input_tokens`~~
   **Answered 2026-09-14: yes, a 100% hit on an immediate reread — see Blocker 3.**
   Still open: does the `1h` TTL survive our actual task gaps (needs `EXTRACTION_MODEL`
   on Anthropic to observe on real pipeline runs, not a synthetic back-to-back call).
4. Fable 5.1 vs Sonnet 5 quality on pedigree and table images. Needs a real eval
   set, not a spike.

## Suggested order

**Done:** the model-name seam, base64 vision images and honest VLM failure handling
(#138); Blocker 1 — the `litellm` bump pinned at 1.100.0 — plus the routing branch
and the litellm-backed `vision.py` (PR A); an `ANTHROPIC_API_KEY` deployed to
dev-caa (#181); **the `VLM_MODEL` flip to `anthropic/claude-fable-5-1`** (#182,
graded against the current OpenAI model on a real pedigree and a real corrupted
table from dev-caa — Fable won clearly on both); **caching, wired and executed**
against a live Anthropic response (#183 — see Blocker 3), ahead of where this list
originally put it, since it did not turn out to need the `EXTRACTION_MODEL` flip
to land, only to matter; **the chat feature deleted outright** rather than carried
through the sessions refactor (2026-09-14, migration
`4993494a8281_drop_the_chat_feature.py`), which removed one of Blocker 2's two
Responses-API-direct call sites and `responses_api_model()` itself ahead of
schedule; **the sessions refactor** (2026-09-14, `lib/tasks/agent_session.py`,
migration `99bb61eac734_drop_tasks_conversation_id_column.py`) — see Blocker 2 for
what shipped differently than planned; **the union-type schema limit found and
fixed for the 4 affected agents** (2026-09-15, `lib/agents/manual_output.py`) —
see Blocker 4 — discovered only once a live paper was actually run end-to-end
against `claude-sonnet-5`, which is why it wasn't on this list until then, and
verified with a second live run (8/8 calls succeeded on the first attempt);
**observability — tracing disabled and the `RunConfig(trace_metadata)` blocks
replaced** (2026-09-22, `lib/core/agents_init.py`, `log_run_metrics`) — see
*Observability gap* — closing what had been the only remaining blocker to the
`EXTRACTION_MODEL` flip.

1. **Run the pipeline end-to-end on OpenAI.** Needs only an `OPENAI_API_KEY` and no
   Anthropic involvement. This is now the highest-priority item: #138 replaced the
   vision image path (base64) and rewrote VLM failure handling, and **neither has
   ever run against a real model on either provider**. That is merged-to-`main` code
   with no end-to-end coverage, and the risk is live today, independent of any
   Anthropic work. The README has a ready case (MASP1, PMID 26419238).
2. ~~**Observability**, as its own PR — actually disable tracing this time~~
   **Landed 2026-09-22** — see *Observability gap*. `set_tracing_disabled(True)`
   runs process-wide via `lib/core/agents_init.py`; the three
   `RunConfig(trace_metadata=...)` blocks were replaced by `log_run_metrics` calls
   carrying the same run-level metadata, plus the zero-tool-call alarm. **This was
   the only remaining blocker to the `EXTRACTION_MODEL` flip** — Blocker 4 (the
   union-type schema limit) looked like a second one when it surfaced mid-live-test,
   but was already fixed and verified, so it didn't add a step here. The flip
   itself is now unblocked from this side but has not been made — that's a
   separate decision. Caching (already wired) starts paying off on the real
   15-turn/25-turn tool loops
   without any further change.

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

Add `--with 'litellm==1.100.0'` after `uv run` to see the native path instead.
