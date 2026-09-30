"""Manual JSON output for schemas too complex for provider-side enforcement.

Patient and variant extraction wrap most fields in EvidenceBlock (value,
reasoning, citations plus the legacy quote/table_id/image_id -- see
lib/models/evidence_block.py), and Pydantic shares
that definition once regardless of how many fields reuse it. Anthropic's tool
schema compiler doesn't: it has to fully dereference every $ref to build its
decoding grammar, and caps the result at 16 union/nullable nodes. Variant's
schema dereferences to 61, patient's to 18 -- both over the limit, confirmed
against a live paper (docs/anthropic-migration.md). Restructuring EvidenceBlock
would fix it, but is a much larger change (touches every agent, every stored
evidence blob, and the UI that renders them) for a problem four agents have
today.

So for exactly the agents whose schema needs it, we send no schema at all --
`Agent(output_type=None)` makes every provider return plain text (see
agents.agent_output.AgentOutputSchema.is_plain_text) -- and describe the shape
in the prompt instead, then validate the response ourselves. This runs
identically regardless of which provider is configured: the fix is "this
agent's schema is too complex for structured output," a fact about the agent,
not about which model happens to be running it today. A schema Anthropic
rejects is not something OpenAI needs a different code path for.
"""

import json
import logging
import re
from collections.abc import Callable
from typing import Any, TypeVar

from agents import Agent, Runner, RunResult, TResponseInputItem
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)

_JSON_OUTPUT_DIRECTIVE = (
    'Respond with a single JSON object and nothing else -- no markdown code '
    'fences, no commentary before or after. It must validate against this '
    'JSON Schema exactly:\n\n{schema}\n\n'
    'The schema above cannot express one of its own rules, because it is a '
    'cross-field check: any object shaped like {{"value", "reasoning", '
    '"citations", ...}} is an evidence block, and citations MUST hold at '
    'least one {{"anchor", "quote"}} entry unless value is null, "Unknown", '
    'or false. A block whose value is a concrete answer but whose citations '
    'list is empty is invalid and will be rejected. The block-level quote, '
    'table_id, image_id and is_supplement fields are legacy: leave them '
    'null / false. If the value itself was constructed rather than copied '
    'verbatim (an invented label, an identifier assigned by you, a '
    'conclusion that follows from a rule rather than from new text), cite '
    'the block that supports the underlying fact instead of leaving '
    'citations empty.'
)

_REPAIR_PROMPT = (
    'That response was not valid JSON matching the required schema:\n\n'
    '{error}\n\nRespond again with ONLY the corrected JSON object -- no '
    'markdown fences, no commentary.'
)

_CHECK_REPAIR_PROMPT = (
    'That output was rejected:\n\n{error}\n\nProduce the complete output '
    'again with those corrected and everything else unchanged.'
)

Check = Callable[[Any], None]

# What a handler sends: one string, or the list `lib.tasks.handlers.paper_input`
# builds (the paper block as its own message, then the task text) so the paper
# can end at a prompt-cache breakpoint.
AgentInput = str | list[TResponseInputItem]

_FENCE_RE = re.compile(r'^```(?:json)?\s*\n?(.*?)\n?```$', re.DOTALL)


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    match = _FENCE_RE.match(text)
    return match.group(1).strip() if match else text


def _append_to_instructions(message: AgentInput, text: str) -> AgentInput:
    """Add `text` to the agent's instructions: the string itself, or the
    instructions item of a list input built by `lib.tasks.handlers.paper_input`
    (item 1; the data item after it, if any, is left alone, as is the paper
    item before it). Both shared items must stay byte-identical across runs
    to be prompt-cache hits, and the directive is the same for every run of
    an agent, so it belongs with the instructions, not with the run's data."""
    if isinstance(message, str):
        return f'{message}\n\n{text}'
    if len(message) < 2:
        raise ValueError('a list input needs a paper item and an instructions item')
    paper, instructions, *data = message
    content = instructions.get('content')  # type: ignore[union-attr]  # the input-item union
    if not isinstance(content, str):
        raise TypeError('the instructions item must carry string content')
    extended = {**instructions, 'content': f'{content}\n\n{text}'}
    return [paper, extended, *data]  # type: ignore[list-item]


async def run_with_manual_output(
    agent: Agent[Any],
    message: AgentInput,
    output_type: type[T],
    *,
    check: Check | None = None,
    max_attempts: int = 3,
    **runner_kwargs: Any,
) -> tuple[RunResult, T]:
    """Run an agent (whose own `output_type` must be None) and validate its
    reply against `output_type` client-side, repairing in the same session up
    to `max_attempts` times if the model's JSON doesn't parse or validate.

    `check` is a further rule the schema cannot express, run on the parsed
    model; a `ValueError` it raises is repaired the same way, with its message
    as the feedback (see `verify_citations` in lib.models.evidence_block).
    """
    directive = _JSON_OUTPUT_DIRECTIVE.format(
        schema=json.dumps(output_type.model_json_schema(), indent=2)
    )
    prompt = _append_to_instructions(message, directive)

    result = await Runner.run(agent, prompt, **runner_kwargs)
    for attempt in range(1, max_attempts + 1):
        text = _strip_code_fence(str(result.final_output))
        try:
            parsed = output_type.model_validate_json(text)
            if check is not None:
                check(parsed)
            return result, parsed
        except (ValidationError, ValueError) as exc:
            if attempt == max_attempts:
                raise
            logger.warning(
                'Manual JSON output for %s failed validation (attempt %d/%d): %s',
                agent.name,
                attempt,
                max_attempts,
                exc,
            )
            result = await Runner.run(
                agent,
                _REPAIR_PROMPT.format(error=exc),
                **runner_kwargs,
            )
    raise AssertionError('unreachable: loop always returns or raises')


async def run_with_checked_output(
    agent: Agent[Any],
    message: AgentInput,
    check: Check,
    *,
    max_attempts: int = 3,
    **runner_kwargs: Any,
) -> RunResult:
    """Run an agent with provider-enforced structured output, then apply a
    rule the schema cannot express, repairing in the same session up to
    `max_attempts` times if `check` raises `ValueError`.

    The native-schema counterpart of `run_with_manual_output`'s `check`: the
    provider already guarantees the shape, so only the cross-document rule
    (citations naming real blocks) can still fail here. The repair turn quotes
    the error back and asks for the whole output again; the provider re-applies
    the schema to that turn as to any other.
    """
    result = await Runner.run(agent, message, **runner_kwargs)
    for attempt in range(1, max_attempts + 1):
        try:
            check(result.final_output)
            return result
        except ValueError as exc:
            if attempt == max_attempts:
                raise
            logger.warning(
                'Output for %s failed its check (attempt %d/%d): %s',
                agent.name,
                attempt,
                max_attempts,
                exc,
            )
            result = await Runner.run(
                agent,
                _CHECK_REPAIR_PROMPT.format(error=exc),
                **runner_kwargs,
            )
    raise AssertionError('unreachable: loop always returns or raises')
