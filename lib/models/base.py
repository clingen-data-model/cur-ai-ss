from pydantic import BaseModel
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class PatchModel(BaseModel):
    def apply_to(self, obj: Base) -> None:
        for field, value in self.model_dump(exclude_unset=True).items():
            setattr(obj, field, value)

    def apply_human_edit_notes(self, obj: Base) -> None:
        """Apply human edit notes to evidence blocks.

        Automatically maps fields ending in '_human_edit_note' to their corresponding
        '_evidence' columns and updates the 'human_edit_note' key within the evidence dict.
        """
        for field, value in self.model_dump(exclude_unset=True).items():
            if field.endswith('_human_edit_note'):
                # Map human_edit_note field to evidence column
                evidence_column = field.replace('_human_edit_note', '_evidence')
                evidence_dict = getattr(obj, evidence_column, {}).copy()
                evidence_dict['human_edit_note'] = value
                setattr(obj, evidence_column, evidence_dict)
