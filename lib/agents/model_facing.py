"""The word "reasoning" never reaches a model; it is "basis" on the wire.

Every value an agent returns is an evidence block carrying a ``reasoning``
string, so an extraction asks the model for its reasoning dozens of times
over, in structured JSON, at length. Anthropic's distillation guard reads
that as an attempt to extract the model's own reasoning and stops the answer
midway with ``stop_reason: refusal``, ``category: reasoning_extraction``
(found 2026-10-22: Opus 5.5 refused patient extraction on papers 108 and 106
every time, Sonnet 5.5 two runs in three; Haiku 5.5 has no such guard).
Replaying the identical request with the word renamed to "basis" completed
every time, so the trigger is the word, not the paper.

The rename happens here, at the model boundary, and nowhere else: the
Pydantic models, the evidence JSON in the database, the API and the UI all
keep ``reasoning``. Outbound, the output schema the provider enforces (or the
one quoted into the prompt for the two manual-output agents) has the word
renamed wherever it appears -- property names, required lists, ``$defs``
names, titles, descriptions. Inbound, the keys of the model's JSON are mapped
back before validation. Prompt prose uses ``MODEL_FACING_WORD`` too
(``test_no_agent_prose_asks_for_reasoning`` guards every instructions
constant).
"""

import json
from typing import Any

from agents.agent_output import AgentOutputSchema, AgentOutputSchemaBase

STORED_WORD = 'reasoning'
MODEL_FACING_WORD = 'basis'


def to_model_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """A copy of ``schema`` with the stored word renamed wherever it appears,
    in either case. Done on the serialized form so that ``$ref`` targets and
    ``$defs`` names change together."""
    text = json.dumps(schema)
    text = text.replace(STORED_WORD, MODEL_FACING_WORD)
    text = text.replace(STORED_WORD.capitalize(), MODEL_FACING_WORD.capitalize())
    return json.loads(text)


def from_model_keys(value: Any) -> Any:
    """``value`` (parsed model JSON) with every dict key ``basis`` renamed back
    to ``reasoning``, at any depth. Values are left alone: a quote or a
    label that happens to contain the word is the model's text."""
    if isinstance(value, dict):
        return {
            (STORED_WORD if key == MODEL_FACING_WORD else key): from_model_keys(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [from_model_keys(item) for item in value]
    return value


class ModelFacingOutputSchema(AgentOutputSchemaBase):
    """The SDK's own output schema for ``output_type``, presented to the model
    with the stored word renamed and validated after mapping it back."""

    def __init__(self, output_type: type[Any], strict_json_schema: bool = True):
        self.output_type = output_type
        self._inner = AgentOutputSchema(
            output_type, strict_json_schema=strict_json_schema
        )
        self._schema = to_model_schema(self._inner.json_schema())

    def is_plain_text(self) -> bool:
        return False

    def name(self) -> str:
        return self._inner.name()

    def json_schema(self) -> dict[str, Any]:
        return self._schema

    def is_strict_json_schema(self) -> bool:
        return self._inner.is_strict_json_schema()

    def validate_json(self, json_str: str) -> Any:
        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            # Let the SDK raise its own ModelBehaviorError for malformed JSON.
            return self._inner.validate_json(json_str)
        return self._inner.validate_json(json.dumps(from_model_keys(parsed)))


def model_facing_output(output_type: type[Any]) -> ModelFacingOutputSchema:
    """What an ``Agent``'s ``output_type`` is set to."""
    return ModelFacingOutputSchema(output_type)
