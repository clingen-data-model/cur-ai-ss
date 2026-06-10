from typing import Literal

from pydantic import BaseModel

from lib.models.evidence_block import ReasoningBlock


class MondoLink(BaseModel):
    """A resolved MONDO link returned by the API."""

    mondo_id: str
    term: str
    confidence: Literal['high', 'medium', 'low'] | None = None


def mondo_link_to_reasoning_block(
    mondo_id: str | None,
    mondo_term: str | None,
    mondo_match_context: dict | None,
) -> ReasoningBlock[MondoLink | None]:
    """Reconstruct a MONDO ReasoningBlock from flattened DB columns."""
    context = mondo_match_context or {}
    confidence = context.get('confidence')
    reasoning = context.get('agent_reasoning')
    if not isinstance(reasoning, str) or not reasoning.strip():
        reasoning = 'MONDO linking not yet performed'

    if not mondo_id or not mondo_term:
        return ReasoningBlock[MondoLink | None](
            value=None,
            reasoning=reasoning,
        )

    return ReasoningBlock[MondoLink | None](
        value=MondoLink(
            mondo_id=mondo_id,
            term=mondo_term,
            confidence=confidence,
        ),
        reasoning=reasoning,
    )
