from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from lib.models.base import Base

if TYPE_CHECKING:
    from lib.models.user import UserDB

# One nullable FK column per trackable entity type ("exclusive arc"), rather
# than a generic entity_type/entity_id pair. A generic pair can never be a
# real FK -- entity_id points at a different table depending on entity_type --
# so deleting a patient/variant/etc. would leave orphaned edit rows unless
# every delete endpoint remembered to clean them up by hand. Each column here
# is a real FK with ON DELETE CASCADE, so history is cleaned up for free by
# the same mechanism every other cascade in this app already relies on.
_ENTITY_FK_COLUMNS: dict[str, str] = {
    'patients': 'patient_id',
    'variants': 'variant_id',
    'patient_variant_occurrences': 'occurrence_id',
    'families': 'family_id',
    'papers': 'paper_id',
    'segregation_evidence': 'segregation_evidence_id',
}


class EditDB(Base):
    """Append-only per-field edit history, replacing the edited_by_user_id/
    edited_by_name/edited_at that used to be duplicated inside every
    HumanEvidenceBlock's own evidence JSON. One row per edit (not per field),
    so the full history survives, not just the most recent edit."""

    __tablename__ = 'edits'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    patient_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('patients.id', ondelete='CASCADE'), nullable=True
    )
    variant_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('variants.id', ondelete='CASCADE'), nullable=True
    )
    occurrence_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('patient_variant_occurrences.id', ondelete='CASCADE'),
        nullable=True,
    )
    family_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('families.id', ondelete='CASCADE'), nullable=True
    )
    paper_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=True
    )
    segregation_evidence_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('segregation_evidence.id', ondelete='CASCADE'),
        nullable=True,
    )

    field_name: Mapped[str] = mapped_column(String, nullable=False)

    # user_id is the source of truth for who made the edit, resolved live via
    # the relationship below rather than a frozen name snapshot -- this app
    # never hard-deletes a user row (accounts are deactivated via
    # UserDB.is_active instead), so user_id is expected to always resolve.
    # ON DELETE SET NULL remains as a defensive fallback for that not holding.
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True
    )
    edited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped['UserDB | None'] = relationship('UserDB')

    __table_args__ = (
        CheckConstraint(
            '(patient_id IS NOT NULL) + (variant_id IS NOT NULL) + '
            '(occurrence_id IS NOT NULL) + (family_id IS NOT NULL) + '
            '(paper_id IS NOT NULL) + (segregation_evidence_id IS NOT NULL) = 1',
            name='ck_edits_exactly_one_entity',
        ),
        Index('ix_edits_patient_id_field_name', 'patient_id', 'field_name'),
        Index('ix_edits_variant_id_field_name', 'variant_id', 'field_name'),
        Index('ix_edits_occurrence_id_field_name', 'occurrence_id', 'field_name'),
        Index('ix_edits_family_id_field_name', 'family_id', 'field_name'),
        Index('ix_edits_paper_id_field_name', 'paper_id', 'field_name'),
        Index(
            'ix_edits_segregation_evidence_id_field_name',
            'segregation_evidence_id',
            'field_name',
        ),
    )


def _entity_fk(obj: Base) -> tuple[str, int]:
    table_name = obj.__tablename__  # type: ignore[attr-defined]
    if table_name not in _ENTITY_FK_COLUMNS:
        raise ValueError(f'{table_name!r} rows do not carry field-edit history')
    entity_id = obj.id  # type: ignore[attr-defined]
    return _ENTITY_FK_COLUMNS[table_name], entity_id


def record_edit(session: Session, obj: Base, field_name: str, editor: 'UserDB') -> None:
    """Append one edit-history row for a single field on ``obj``.

    Flushes immediately: the app's sessionmaker runs with autoflush=False, and
    a response built later in the same request (via latest_edits_for) must see
    this row, not just whatever gets flushed on the next unrelated query."""
    record_edits(session, obj, [field_name], editor)


def record_edits(
    session: Session, obj: Base, field_names: list[str], editor: 'UserDB'
) -> None:
    """Append one edit-history row per field in ``field_names`` on ``obj``, in a
    single flush -- e.g. every manually-entered field at creation time, once
    the row has been flushed and has a real id for the FK to point at."""
    fk_column, entity_id = _entity_fk(obj)
    now = datetime.now(timezone.utc)
    for field_name in field_names:
        session.add(
            EditDB(
                field_name=field_name,
                user_id=editor.id,
                edited_at=now,
                **{fk_column: entity_id},
            )
        )
    session.flush()


def latest_edits_for(session: Session, obj: Base) -> dict[str, EditDB]:
    """The most recent edit row per field_name for ``obj``, keyed by field_name."""
    fk_column, entity_id = _entity_fk(obj)
    rows = (
        session.execute(
            select(EditDB)
            .where(getattr(EditDB, fk_column) == entity_id)
            .order_by(EditDB.edited_at.desc())
        )
        .scalars()
        .all()
    )
    latest: dict[str, EditDB] = {}
    for row in rows:
        latest.setdefault(row.field_name, row)
    return latest
