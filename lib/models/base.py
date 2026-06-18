from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlalchemy.orm import DeclarativeBase

if TYPE_CHECKING:
    from lib.models.user import UserDB


class Base(DeclarativeBase):
    pass


def row_to_dict(obj: Base) -> dict:
    """Dump all mapped columns of an ORM row to a plain dict."""
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def _editor_display_name(editor: UserDB) -> str:
    name = f'{editor.first_name} {editor.last_name}'.strip()
    return name or editor.email


class PatchModel(BaseModel):
    def apply_to(self, obj: Base, editor: UserDB | None = None) -> None:
        for field, value in self.model_dump(exclude_unset=True).items():
            self._apply_field(obj, field, value, editor)
        self.stamp_updated_by(obj, editor)

    @staticmethod
    def _apply_field(
        obj: Base, field: str, value: object, editor: UserDB | None
    ) -> None:
        """Apply one patched field, mapping ``*_human_edit_note`` to its evidence
        column and stamping per-field edit attribution onto that evidence block."""
        if field.endswith('_human_edit_note'):
            evidence_column = field.replace('_human_edit_note', '_evidence')
            existing = getattr(obj, evidence_column, None)
            if not existing:
                # Nothing to annotate — e.g. an optional field that was never
                # extracted (nullable evidence column). Skip rather than write an
                # invalid note-only block that would fail HumanEvidenceBlock validation.
                return
            evidence_dict = existing.copy()
            evidence_dict['human_edit_note'] = value
            if editor is not None:
                evidence_dict['edited_by_user_id'] = editor.id
                evidence_dict['edited_by_name'] = _editor_display_name(editor)
                evidence_dict['edited_at'] = datetime.now(timezone.utc).isoformat()
            setattr(obj, evidence_column, evidence_dict)
        else:
            setattr(obj, field, value)

    @staticmethod
    def stamp_updated_by(obj: Base, editor: UserDB | None) -> None:
        """Record which user last edited ``obj`` (no-op for machine writes)."""
        if editor is not None and hasattr(obj, 'updated_by_user_id'):
            obj.updated_by_user_id = editor.id
