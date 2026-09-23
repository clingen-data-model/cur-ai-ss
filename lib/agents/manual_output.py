"""Manual JSON output for schemas too complex for provider-side enforcement.

Patient and variant extraction wrap most fields in EvidenceBlock (value, quote,
table_id, image_id -- see lib/models/evidence_block.py), and Pydantic shares
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
from typing import Any, TypeVar

from agents import Agent, Runner, RunResult
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)

_JSON_OUTPUT_DIRECTIVE = (
    'Respond with a single JSON object and nothing else -- no markdown code '
    'fences, no commentary before or after. It must validate against this '
    'JSON Schema exactly:\n\n{schema}\n\n'
    'The schema above cannot express one of its own rules, because it is a '
    'cross-field check: any object shaped like {{"value", "reasoning", '
    '"quote", "table_id", "image_id", ...}} is an evidence block, and at '
    'least one of quote, table_id, or image_id MUST be set unless value is '
    'null, "Unknown", or false. A block whose value is a concrete answer but '
    'whose quote/table_id/image_id are all empty is invalid and will be '
    'rejected. If the value itself was constructed rather than copied '
    'verbatim (an invented label, an identifier assigned by you, a '
    'conclusion that follows from a rule rather than from new text), cite '
    'whatever quote, table, or image supports the underlying fact instead '
    'of leaving all three empty.'
)

_REPAIR_PROMPT = (
    'That response was not valid JSON matching the required schema:\n\n'
    '{error}\n\nRespond again with ONLY the corrected JSON object -- no '
    'markdown fences, no commentary.'
)

_FENCE_RE = re.compile(r'^```(?:json)?\s*\n?(.*?)\n?```$', re.DOTALL)


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    match = _FENCE_RE.match(text)
    return match.group(1).strip() if match else text


async def run_with_manual_output(
    agent: Agent[Any],
    message: str,
    output_type: type[T],
    *,
    max_attempts: int = 3,
    **runner_kwargs: Any,
) -> tuple[RunResult, T]:
    """Run an agent (whose own `output_type` must be None) and validate its
    reply against `output_type` client-side, repairing in the same session up
    to `max_attempts` times if the model's JSON doesn't parse or validate.
    """
    prompt = f'{message}\n\n' + _JSON_OUTPUT_DIRECTIVE.format(
        schema=json.dumps(output_type.model_json_schema(), indent=2)
    )

    result = await Runner.run(agent, prompt, **runner_kwargs)
    for attempt in range(1, max_attempts + 1):
        text = _strip_code_fence(str(result.final_output))
        try:
            return result, output_type.model_validate_json(text)
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
