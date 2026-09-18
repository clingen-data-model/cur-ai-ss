from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel
from sqlalchemy.orm import DeclarativeBase

from lib.models.evidence_block import HumanEvidenceBlock

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


def manual_evidence_block(value: Any, editor: UserDB) -> dict:
    """Evidence block for a field a curator typed directly rather than one the
    extraction pipeline found -- e.g. a manually created patient/variant/family/
    occurrence. Every ``*_evidence`` column is non-nullable, and PatchModel's
    ``*_human_edit_note`` handling requires an existing evidence dict to
    annotate, so these fields need a real (if reasoning-less) evidence block
    from the moment the row is created, not just on later extraction."""
    block = HumanEvidenceBlock[Any](
        value=value,
        reasoning='Manually entered by curator.',
        manually_entered=True,
        human_edit_note='Manually entered by curator.',
        edited_by_user_id=editor.id,
        edited_by_name=_editor_display_name(editor),
        edited_at=datetime.now(timezone.utc),
    )
    return block.model_dump(mode='json')


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
