from datetime import datetime
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
    is_supplement: bool = (
        False  # whether evidence came from a supplement (non-renderable in PDF view)
    )

    @model_validator(mode='after')
    def validate_sources(self) -> Self:
        if not self.reasoning.strip():
            raise ValueError('reasoning must be non-empty')

        # Skip evidence source requirement if value is None or UNKNOWN
        is_unknown = (
            self.value is None
            or self.value == 'Unknown'
            or (hasattr(self.value, 'value') and self.value.value == 'Unknown')
        )

        # For boolean values, skip validation if value is falsy (no evidence required for False)
        is_falsy_bool = isinstance(self.value, bool) and not self.value

        if (
            not is_unknown
            and not is_falsy_bool
            and not self.quote
            and self.table_id is None
            and self.image_id is None
        ):
            raise ValueError(
                'At least one evidence source must be provided: '
                'quote, table_id, or image_id'
            )

        # Prioritize table_id if both are provided
        if self.table_id is not None and self.image_id is not None:
            self.image_id = None

        return self


class HumanEvidenceBlock(EvidenceBlock[T]):
    human_edit_note: str | None = None  # optional annotation by human curator
    # Per-field edit attribution. ``edited_by_name`` is an immutable snapshot of
    # the curator's display name at edit time (deletion/rename-proof); the id is
    # a soft link only (no FK is possible inside a JSON column).
    edited_by_user_id: int | None = None
    edited_by_name: str | None = None
    edited_at: datetime | None = None
