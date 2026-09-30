"""A repair loop for the rule an output schema cannot express.

Every agent runs with provider-enforced structured output (`Agent(output_type=
<Model>)`), so the shape of a reply is guaranteed before it reaches us. What the
schema cannot say is that a citation must name a block the paper actually has
and quote text that block contains (`verify_citations` in
lib.models.evidence_block). `run_with_checked_output` applies that check after
the run and, when it fails, sends the message back to the model as a repair
turn in the same session, up to `max_attempts` times.

History: until slice 4 of docs/evidence-anchors-plan.md this module also held
`run_with_manual_output`, which sent no schema to the provider and validated
the reply client-side for the four agents whose schema exceeded Anthropic's
16-union-node limit. The legacy nullable fields that put them over the limit
are gone, so every agent is native now (test_output_schema_census pins the
counts; docs/anthropic-migration.md, Blocker 4, has the story).
"""

import logging
from collections.abc import Callable
from typing import Any

from agents import Agent, Runner, RunResult, TResponseInputItem

logger = logging.getLogger(__name__)

_CHECK_REPAIR_PROMPT = (
    'That output was rejected:\n\n{error}\n\nProduce the complete output '
    'again with those corrected and everything else unchanged.'
)

Check = Callable[[Any], None]

# What a handler sends: one string, or the list `lib.tasks.handlers.paper_input`
# builds (the paper block as its own message, then the task text) so the paper
# can end at a prompt-cache breakpoint.
AgentInput = str | list[TResponseInputItem]


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

    The provider already guarantees the shape, so only the cross-document rule
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
