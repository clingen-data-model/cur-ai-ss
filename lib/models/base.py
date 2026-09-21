from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel
from sqlalchemy.orm import DeclarativeBase

from lib.models.evidence_block import HumanEvidenceBlock

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from lib.models.user import UserDB


class Base(DeclarativeBase):
    pass


def row_to_dict(obj: Base) -> dict:
    """Dump all mapped columns of an ORM row to a plain dict."""
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def _editor_display_name(editor: UserDB) -> str:
    name = f'{editor.first_name} {editor.last_name}'.strip()
    return name or editor.email


def manual_evidence_block(value: Any) -> dict:
    """Evidence block for a field a curator typed directly rather than one the
    extraction pipeline found -- e.g. a manually created patient/variant/family/
    occurrence. Every ``*_evidence`` column is non-nullable, and PatchModel's
    ``*_human_edit_note`` handling requires an existing evidence dict to
    annotate, so these fields need a real (if reasoning-less) evidence block
    from the moment the row is created, not just on later extraction.

    Carries no attribution itself: the entity doesn't have a primary key yet
    at the point this is called (it's building the columns passed into the
    ORM constructor), so there's nothing yet for an edits row's foreign key
    to point at. The caller records the real edits-table row once the row has
    been flushed and has an id -- see record_edit() calls in create_patient/
    create_variant/create_occurrence/create_family."""
    block = HumanEvidenceBlock[Any](
        value=value,
        reasoning='Manually entered by curator.',
        manually_entered=True,
        human_edit_note='Manually entered by curator.',
    )
    return block.model_dump(mode='json')


class PatchModel(BaseModel):
    def apply_to(
        self, obj: Base, editor: UserDB | None = None, session: Session | None = None
    ) -> None:
        updates = self.model_dump(exclude_unset=True)
        # Snapshot each value field's pre-patch value before *any* field is
        # applied, then apply value fields before note fields -- a
        # `<field>_human_edit_note` always arrives alongside its `<field>` in
        # the same request (see HumanEditNoteDialog call sites), and recording
        # edit history for it needs both the value from before this patch and
        # the value from after it, not whatever order model_dump() happens to
        # iterate the two in.
        old_values = {
            field: getattr(obj, field, None)
            for field in updates
            if not field.endswith('_human_edit_note')
        }
        note_fields = [f for f in updates if f.endswith('_human_edit_note')]
        for field in updates:
            if field not in note_fields:
                self._apply_field(obj, field, updates[field], editor, session)
        for field in note_fields:
            self._apply_field(obj, field, updates[field], editor, session, old_values)
        self.stamp_updated_by(obj, editor)

    @staticmethod
    def _apply_field(
        obj: Base,
        field: str,
        value: object,
        editor: UserDB | None,
        session: Session | None = None,
        old_values: dict[str, Any] | None = None,
    ) -> None:
        """Apply one patched field, mapping ``*_human_edit_note`` to its evidence
        column and recording per-field edit history for it."""
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
            setattr(obj, evidence_column, evidence_dict)
            if editor is not None and session is not None:
                # Local import: edit.py imports Base from this module, so a
                # top-level import here would be circular.
                from lib.models.edit import record_edit

                field_name = field.replace('_human_edit_note', '')
                record_edit(
                    session,
                    obj,
                    field_name,
                    editor,
                    old_value=(old_values or {}).get(field_name),
                    new_value=getattr(obj, field_name, None),
                )
        else:
            setattr(obj, field, value)

    @staticmethod
    def stamp_updated_by(obj: Base, editor: UserDB | None) -> None:
        """Record which user last edited ``obj`` (no-op for machine writes)."""
        if editor is not None and hasattr(obj, 'updated_by_user_id'):
            obj.updated_by_user_id = editor.id
