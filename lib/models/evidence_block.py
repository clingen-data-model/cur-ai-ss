from typing import Generic, Self, TypeVar

from pydantic import BaseModel, model_validator

T = TypeVar('T')


class ReasoningBlock(BaseModel, Generic[T]):
    value: T
    reasoning: str  # human-readable summary (always required)


class EvidenceBlock(ReasoningBlock[T]):
    quote: str | None = None  # verbatim quote from text
    table_id: int | None = None  # table-based evidence
    image_id: int | None = None  # figure/pedigree evidence

    @model_validator(mode='after')
    def validate_sources(self) -> Self:
        if not self.reasoning.strip():
            raise ValueError('reasoning must be non-empty')

        # Skip evidence source requirement if value is None or UNKNOWN
        is_unknown = self.value is None or (
            hasattr(self.value, 'value') and self.value.value in ('unknown', 'Unknown')
        )

        # For boolean values, skip validation if value is falsy (no evidence required for False)
        is_falsy_bool = isinstance(self.value, bool) and not self.value

        if (
            not is_unknown
            and not is_falsy_bool
            and not self.quote
            and not self.table_id
            and not self.image_id
        ):
            raise ValueError(
                'At least one evidence source must be provided: '
                'quote, table_id, or image_id'
            )

        if self.table_id is not None and self.image_id is not None:
            raise ValueError('Only one of table_id or image_id may be provided')

        return self


class HumanEvidenceBlock(EvidenceBlock[T]):
    human_edit_note: str | None = None  # optional annotation by human curator
