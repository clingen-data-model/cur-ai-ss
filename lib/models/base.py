from pydantic import BaseModel
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class PatchModel(BaseModel):
    def apply_to(self, obj: Base, updated_by_user_id: int | None = None) -> None:
        for field, value in self.model_dump(exclude_unset=True).items():
            if field.endswith('_human_edit_note'):
                # Map human_edit_note field to evidence column
                evidence_column = field.replace('_human_edit_note', '_evidence')
                evidence_dict = getattr(obj, evidence_column, {}).copy()
                evidence_dict['human_edit_note'] = value
                setattr(obj, evidence_column, evidence_dict)
            else:
                setattr(obj, field, value)
        self.stamp_updated_by(obj, updated_by_user_id)

    @staticmethod
    def stamp_updated_by(obj: Base, updated_by_user_id: int | None) -> None:
        """Record which user last edited ``obj`` (no-op for machine writes)."""
        if updated_by_user_id is not None and hasattr(obj, 'updated_by_user_id'):
            obj.updated_by_user_id = updated_by_user_id
