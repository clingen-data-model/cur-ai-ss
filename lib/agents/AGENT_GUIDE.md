# Writing Agents for the Extraction Pipeline

An agent is an `agents.Agent` (the `openai-agents` package) with a Pydantic output model. A task handler in `lib/tasks/handlers.py` runs it and writes the result to the database. `lib/agents/paper_classifier_agent.py` and `handle_paper_classifier` are the smallest complete pair. `lib/agents/hpo_linking_agent.py` shows an agent with tools.

## Adding an agent

1. **The agent** goes in `lib/agents/<name>_agent.py`:

   ```python
   from agents import Agent

   from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
   from lib.agents.model_facing import model_facing_output
   from lib.agents.model_factory import extraction_model, extraction_model_settings

   MY_AGENT_INSTRUCTIONS = """..."""  # the task prompt, sent by the handler (below)

   agent = Agent(
       name='my_agent',
       instructions=BASE_SYSTEM_INSTRUCTIONS,
       model=extraction_model(),
       model_settings=extraction_model_settings(),
       output_type=model_facing_output(MyOutput),
   )
   ```

   - `instructions` is the shared one-line system prompt. The task prompt goes in a constant that the handler sends as an input item, so the prompt cache can reuse it (see "Sending the paper").
   - Pick the model with a factory in `lib/agents/model_factory.py`:
     - `extraction_model()` for agents that read the paper;
     - `linking_model()` for the many small ontology-linking calls;
     - `vlm_model()` for vision.
   - Model names are `<provider>/<model>`, configured in `lib/core/environment.py`.

2. **The task.** Add a `TaskType` (with its `label` and description) and its edges in `TASK_SUCCESSORS`, both in `lib/tasks/models.py`. A task scoped to a patient, family, variant, phenotype or occurrence also needs its `scope_column`.

3. **The handler.** Add an `async def handle_<name>(task_id: int) -> None` in `lib/tasks/handlers.py` and register it in `TASK_HANDLERS`. The pattern, from `handle_paper_classifier`:
   1. Read the task (its `additional_context`, `context_origin` and `budget_model`) and the rows it needs inside `session_scope()`.
   2. Get `agent_session(task_id)`. Use `continues_conversation` to decide between a follow-up (`build_followup_prompt`) and a fresh first message (`clear_session`, then `paper_input(...)`, then `with_curator_note(...)`).
   3. Run `agent_on_tier(agent, budget_model)`, so a quick run uses `EXTRACTION_BUDGET_MODEL`:
      - with `run_with_checked_output(..., citation_check(paper_id))` when the output carries evidence;
      - otherwise with `Runner.run`;
      - with `run_with_manual_output` when the schema is too big for the provider (see "Schema limits").
   4. Call `log_run_metrics`, then write the output inside `session_scope()` through a converter in `lib/models/converters.py` (`*_to_db`). Then call `replace_flags` if the agent raises flags.

4. **Storage.** Add the model in `lib/models/`, an alembic migration (read the migration rules in CLAUDE.md first), the API fields, and the UI.

## Instructions

Write the task prompt as sections: the task, INPUT, OUTPUT, PROCESS (numbered steps naming the tools to use and when), EXAMPLES, EDGE CASES (negation, missing data, conflicts).
- Write "basis" wherever the prompt means reasoning (see below).
- Keep prompts generic. The paper that motivated a rule (its gene, PMID or phrasing) goes in a code comment, never in the prompt.
- Field descriptions and enums or `Literal` types in the output model steer the model as much as the prose does.

Tools (`@function_tool`) need full type hints. The model reads the docstring to decide when to call a tool, so write it for that. Return structured data, and give each tool one action.

## Evidence and citations

Any extracted value a curator will check goes in an `EvidenceBlock` (`lib/models/evidence_block.py`): `value`, `reasoning`, and `citations`, a list of `{anchor, quote}`.

- **The model never sees the word `reasoning`.** `lib/agents/model_facing.py` presents the field as `basis` in every output schema and maps it back on the reply. Wrap an agent's `output_type` in `model_facing_output(...)`; the manual-output path does this itself. Prompt prose says "basis" too, and `test_no_agent_prose_asks_for_reasoning` checks it. Otherwise Anthropic's `reasoning_extraction` classifier cuts Sonnet and Opus off mid-answer.
- **What the agent reads** is the anchored document (`lib/misc/pdf/anchors.py`):
  - each paragraph is prefixed `[paragraph-N]`;
  - each table `[table-N]`, with an `anchor` column of `table-N-row-R` ids;
  - each figure `[figure-N]`;
  - supplement ids start with `supp-`.
- **How it cites:** it copies an id as printed and gives the shortest exact span of that block that supports the value. For a table row that is the cell's text; for a figure, no quote.
- **The contract** is `CORE_EXTRACTION_SPEC` (`lib/agents/core_extraction_rules.py`). Append it to any prompt that produces evidence blocks.
- **The citation check.** The schema can't check that a cited id exists or that a quote is in its block, so the handler passes `citation_check(paper_id)`. `verify_citations` raises with one line per bad citation, and the runner sends that back to the model as a repair turn in the same session. After three failed attempts the task fails, so nothing with unverified evidence is stored.

## Schema limits

Anthropic limits output schemas in two ways:
- A dereferenced schema may have at most 16 union/nullable nodes.
- Above that, a schema whose compiled grammar is too large is refused. This limit is undocumented: roughly 20 objects, and each `EvidenceBlock` counts as two once `Citation` is inlined.

`test/agents/test_output_schema_census.py` fails if an agent's schema goes over the union limit. It also pins which agents run without a native schema. Variant extraction and demographics use `output_type=None` and `run_with_manual_output` (`lib/agents/manual_output.py`), which puts the schema in the prompt and validates the reply client-side. Keep both limits in mind when adding fields to an output model.

## Flags

A decision a curator should look at but the output can't show goes in a `flags` list on the output model (`lib/models/flag.py`). Examples are something left out under a rule, or a call the paper leaves open.

- **Types:**
  - `ExtractionFlag`, an evidence block, for agents that read the paper;
  - `ReasoningFlag`, a reasoning block, for lookup agents with nothing to cite;
  - an agent whose whole output is one `ReasoningBlock` returns a `FlaggedReasoningBlock` instead.
- **`kind`** is one of the closed `FlagKind` list: excluded, conflict, ambiguous, inferred, unresolved, mismatch. A prompt's FLAGS section says which kinds that task may raise. A decision that fits none of them is not a flag.
- **`about`** is the identifier of the thing the flag concerns, or null.
- **`FLAG_RULES`** (`lib/agents/core_extraction_rules.py`) states the rule once. It is inside `CORE_EXTRACTION_SPEC` for the paper-reading agents and appended directly by the lookup agents. A prompt adds at most a few task-specific examples.
- **The handler** calls `replace_flags` (`lib/tasks/flags.py`) after writing its rows. It passes the task's scope and a resolver that turns `about` into the row it just wrote. A flag about a compound-het pair links both occurrences (`occurrence_id`, `paired_occurrence_id`).
- **Endpoints:**
  - `/papers/{id}/flags` lists them;
  - its `/resolve` child resolves a flag, once and for good;
  - `/rerun` queues the raising agent again for its scope, with the curator's note as follow-up context, which replaces the flag with whatever the agent raises next.

The per-entity agents run concurrently and each sees only its own scope, so one decision is often flagged several times in different words. Two examples: a country inferred from the study site gets flagged once per relative; a label that differs from the pedigree gets flagged by patient extraction and again by demographics.

Extraction Verification is the pipeline's last task (`lib/agents/extraction_verification_agent.py`, `lib/tasks/extraction_verification.py`). It folds each repeated decision into its earliest flag:
- the absorbed flags are deleted;
- their agent, row and subject are appended to the surviving flag's reasoning;
- the survivor keeps only the links the group agreed on: the family when the patients differ but share one, nothing when they don't.

The worker queues it whenever a paper settles, so an agent's prompt never needs to know what another agent flagged.

## Sending the paper

Send the paper through `paper_input(format_paper_context(markdown, gene_symbol), INSTRUCTIONS, task_data)`, never inlined into the task text. It gives the runner three input items in this order:
1. the paper block: the paper plus the gene, the same bytes for every agent;
2. the agent's instruction constant: the same bytes for every run of that agent;
3. this run's data (patient JSON, variants JSON, ...). Omit `task_data` for an agent that reads only the paper.

Get the markdown from `paper_text`, which inserts each figure description under its figure id.

The prompt-cache breakpoints in `lib/agents/model_factory.py` target those items by position. Every agent on a paper then reuses the paper block the first one sent, and every run of one agent after the first reuses its instructions. That saves resending about 25k tokens of paper and 10k of instructions per call. Write instructions to match this order: the paper is "above", the run's data "below".
