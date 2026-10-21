# Writing Agents for the Extraction Pipeline

Agents use the `openai_agents` library to perform structured extraction with step-by-step reasoning. Each agent defines tools, detailed instructions, and a Pydantic output model.

## Agent Structure

```python
from openai_agents import Agent, function_tool
from pydantic import BaseModel, Field
from lib.core.environment import env

@function_tool
def my_tool(param: str) -> dict:
    """Tool description (LLM reads this docstring)."""
    return result

class MyOutput(BaseModel):
    field: str = Field(description="Output description")

INSTRUCTIONS = """
You are an expert at [task].

INPUT: [describe what the agent receives]
OUTPUT: Return MyOutput with [describe what to extract]

PROCESS
1. [First step]
2. [Second step — use my_tool when...]
3. [Final step]

EXAMPLES
Input: [example] → Output: [example]

EDGE CASES
- When [condition], do [action]
"""

agent = Agent(
    name='my_agent',
    instructions=INSTRUCTIONS,
    model=extraction_model(),  # from lib.agents.model_factory
    output_type=MyOutput,
    tools=[my_tool],
)
```

## Key Components

### Tools (`@function_tool`)

- **Type hints required** for all parameters and return value
- **Docstring is critical** — the LLM reads it to understand when to use the tool
- **Return structured data** (dict, list, BaseModel) — never raw strings
- **One tool per logical action** — avoid mega-tools

```python
@function_tool
def search_database(query: str, limit: int = 10) -> list[dict]:
    """Search database, return list of {id, name, score}."""
    return [{'id': r.id, 'name': r.name, 'score': r.score} for r in db.search(query, limit)]
```

### Instructions

The prompt string should have these sections:

- **Task description** — what you want extracted
- **INPUT** — what data the agent receives
- **OUTPUT** — fields to return with descriptions
- **PROCESS** — numbered steps; mention which tools to use and when
- **EXAMPLES** — one or two concrete examples
- **EDGE CASES** — how to handle negation, missing data, conflicts, etc.

Keep instructions explicit and specific. Don't assume the LLM will infer.

### Output Model

A Pydantic model that defines the agent's return structure. OpenAI uses this as a JSON schema:

```python
class MyOutput(BaseModel):
    field1: str = Field(description="What this contains")
    field2: int | None = Field(default=None, description="Optional field")
    nested: NestedModel = Field(description="Complex field")
```

### Evidence and citations

Any extracted value a curator will check goes in an `EvidenceBlock` (`lib/models/evidence_block.py`):
`value`, `reasoning`, and `citations`, a list of `{anchor, quote}`. The text agents read is
the anchored document (`lib/misc/pdf/anchors.py`): every paragraph is prefixed
`[paragraph-N]`, every table `[table-N]` with an `anchor` column of `table-N-row-R` ids, every
figure `[figure-N]`; supplement ids start with `supp-`. An agent cites by copying an id as
printed and giving the shortest verbatim span of that block that supports the value (a
table cell's text for a row citation, nothing for a figure).

Append `CORE_EXTRACTION_SPEC` (`lib/agents/core_extraction_rules.py`) to any prompt that
produces evidence blocks; it states the contract once. The schema cannot check that a
cited id exists or that a quote is really in its block, so the handler passes
`citation_check(paper_id)` (`lib/tasks/handlers.py`) to the runner: `verify_citations`
(`lib/models/evidence_block.py`) raises with one line per bad citation, and the runner
sends that message back to the model as a repair turn in the same session, up to three
attempts, before the task fails. Nothing with unverified evidence is stored.

Anthropic caps a dereferenced output schema at 16 union/nullable nodes and, above that,
refuses one whose compiled grammar is too large (undocumented; roughly 20 objects, and every
`EvidenceBlock` is two objects once `Citation` is inlined). `test/agents/test_output_schema_census.py`
fails if any agent's schema crosses the union limit and pins which agents run without a
native schema: variant extraction and demographics, whose schemas the grammar compiler
refuses, use `output_type=None` and `run_with_manual_output` (`lib/agents/manual_output.py`),
which puts the schema in the prompt and validates the reply client-side. Every other agent
passes its `output_type` to the runner; the ones whose handler passes `citation_check` get
the same repair loop from `run_with_checked_output`. Keep both limits in mind when adding
fields to an output model.

### Flags

A decision a curator should look at but the output cannot show -- something left out
under a rule, a call the paper leaves open -- goes in a `flags` list on the output model
(`lib/models/flag.py`): `ExtractionFlag` (an evidence block, for agents that read the
paper) or `ReasoningFlag` (a reasoning block, for the lookup agents with nothing to
cite); an agent whose whole output is one `ReasoningBlock` returns a
`FlaggedReasoningBlock` instead. Each flag's `kind` is one of the closed `FlagKind`
list (excluded, conflict, ambiguous, inferred, unresolved, mismatch); a prompt's FLAGS
section says which kinds that task may raise, and a decision that fits none is not a
flag. Each flag's `about` is the identifier of the thing it concerns, or null. `FLAG_RULES` (`lib/agents/core_extraction_rules.py`) states the rule
once -- inside `CORE_EXTRACTION_SPEC` for the paper-reading agents, appended directly by
the lookup agents -- and a prompt adds at most a few task-specific examples. The handler
calls `replace_flags` (`lib/tasks/flags.py`) after writing its rows, with the task's
scope (the patient, family, variant, phenotype or occurrence a per-entity task ran for)
and a resolver that turns `about` into the row it just wrote; a flag about a compound-het
pair links both occurrences (`occurrence_id`, `paired_occurrence_id`). Flags are listed
through `/papers/{id}/flags`, resolved, once and for good, through its `/resolve` child,
and `/rerun` queues the raising agent again for its scope (`TaskType.scope_column`) with
the curator's note as follow-up context -- which replaces the flag with whatever the
agent raises next.

The per-entity agents run concurrently and see only their own scope, so one decision is
often flagged several times in different words (a country inferred from the study site,
once per relative; a label that differs from the pedigree, once by patient extraction
and once by demographics). Extraction verification (`lib/agents/extraction_verification_agent.py`,
`lib/tasks/extraction_verification.py`), the pipeline's last task, reads every open flag
on the paper and folds each repeated decision into its earliest flag: the absorbed
flags are deleted, their agent, row and subject appended to the survivor's reasoning,
and the survivor keeps only the links the group agreed on -- a family when the patients
differ but share one, nothing when they do not. The worker queues it whenever a paper
settles, including after a single re-run, so an agent's prompt does not need to know
what another agent flagged.

## Calling an Agent

```python
from lib.agents.my_agent import agent
from lib.models.converters import convert_to_db_model

result = agent.run(pdf_markdown=content, paper_id=paper_id)

# Save to database
db_entry = convert_to_db_model(result)
session.add(db_entry)
session.commit()
```

Agents are invoked from `lib/bin/worker.py` as part of the extraction pipeline.

**Send the paper through `paper_input`** (`lib/tasks/handlers.py`), never inlined into
the task text: `paper_input(format_paper_context(markdown, gene_symbol), INSTRUCTIONS,
task_data)` gives the runner three input items in this order: the paper block (paper
plus gene, byte-identical across agents), the agent's instruction constant
(byte-identical across runs of that agent), and last the data for this run (patient JSON,
pedigree description,
...). Omit `task_data` for an agent that reads the paper alone. The prompt-cache
breakpoints in `lib/agents/model_factory.py` target those items by position, so every
agent on a paper reads the paper block the first one wrote, and every run of one agent
reads its instructions after the first, instead of re-sending ~25k tokens of paper and
~10k of instructions each call. Write instructions to match the order: the paper is
"above", the run's data "below". `Runner.run` and `run_with_checked_output` both accept
the list.

## Tips

- **Field descriptions matter** — the LLM uses them to understand the schema
- **Examples in instructions** should show the exact output format you want
- **Docstrings are critical** — tool docstrings appear in the agent's reasoning; unclear ones hurt tool usage
- **Use Optional/None** for fields that might not exist
- **Use enum** or literal types to constrain values

## Reference

- **Full example:** See `lib/agents/hpo_linking_agent.py` for a complete agent with multiple tools and edge-case handling
- **Paper files:** `lib/misc/pdf/paths.py` has the path builders for everything kept per paper (`documents/<id>/`: the upload, anchored text, table and figure images)
- **Database conversion:** `lib/models/converters.py` converts agent outputs to database models
- **Config:** `lib/core/environment.py` provides `EXTRACTION_MODEL` / `VLM_MODEL` ('<provider>/<model>' names, prefix required, e.g. `openai/gpt-5.6-luna`) plus `OPENAI_API_KEY`. Agents get their model via `lib/agents/model_factory.extraction_model()`, vision tools via `vlm_model()`.
