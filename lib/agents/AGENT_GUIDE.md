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
    model=env.OPENAI_API_DEPLOYMENT,
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
- **Config:** `lib/core/environment.py` provides `OPENAI_API_KEY`, `OPENAI_API_DEPLOYMENT`
