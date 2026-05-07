from pydantic import BaseModel
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class PatchModel(BaseModel):
    def apply_to(self, obj: Base) -> None:
        for field, value in self.model_dump(exclude_unset=True).items():
            if field.endswith('_human_edit_note'):
                # Map human_edit_note field to evidence column
                evidence_column = field.replace('_human_edit_note', '_evidence')
                evidence_dict = getattr(obj, evidence_column, {}).copy()
                evidence_dict['human_edit_note'] = value
                setattr(obj, evidence_column, evidence_dict)
            else:
                setattr(obj, field, value)
