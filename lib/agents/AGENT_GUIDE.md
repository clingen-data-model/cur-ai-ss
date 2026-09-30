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

## Calling an Agent

```python
from lib.agents.my_agent import agent
from lib.models.converters import convert_to_db_model

result = agent.run(pdf_markdown=content, paper_id=paper_id)

# Save to database
db_entry = convert_to_db_model(result)
session.add(db_entry)
session.commit()

# Save JSON alongside PDF
output_path = pdf_json_path(paper_id, 'my_agent')
output_path.write_text(result.model_dump_json(indent=2))
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
- **Output storage:** `lib/misc/pdf/paths.py` has path builders for storing JSON outputs
- **Database conversion:** `lib/models/converters.py` converts agent outputs to database models
- **Config:** `lib/core/environment.py` provides `EXTRACTION_MODEL` / `VLM_MODEL` ('<provider>/<model>' names, prefix required, e.g. `openai/gpt-5.6-luna`) plus `OPENAI_API_KEY`. Agents get their model via `lib/agents/model_factory.extraction_model()`, vision tools via `vlm_model()`.
