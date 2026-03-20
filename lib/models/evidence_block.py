from typing import Generic, Self, TypeVar

from pydantic import BaseModel, model_validator

T = TypeVar('T')


class EvidenceBlock(BaseModel, Generic[T]):
    value: T
    evidence_context: str | None = None  # verbatim quote from text
    table_id: int | None = None  # table-based evidence
    image_id: int | None = None  # figure/pedigree evidence
    reasoning: str  # human-readable summary (always required)

    @model_validator(mode='after')
    def validate_sources(self) -> Self:
        if not self.reasoning.strip():
            raise ValueError('reasoning must be non-empty')

        if not self.evidence_context and not self.table_id and not self.image_id:
            raise ValueError(
                'At least one evidence source must be provided: '
                'evidence_context, table_id, or image_id'
            )

        if self.table_id is not None and self.image_id is not None:
            raise ValueError('Only one of table_id or image_id may be provided')

        return self
