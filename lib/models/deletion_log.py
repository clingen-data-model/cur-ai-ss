from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from lib.models.base import Base
from lib.models.datetimes import UtcDatetime
from lib.models.user import UserSummaryResp

if TYPE_CHECKING:
    from lib.models.user import UserDB


class DeletionLogDB(Base):
    """Append-only record of a curator deleting a patient/variant/occurrence/
    phenotype/paper -- the delete itself is otherwise silent and unrecoverable.

    Deliberately carries no foreign key back into the entity it records (not
    even ``paper_id``, which is a plain snapshot int rather than a real FK):
    every entity table this app tracks deletes CASCADE, so a row FK'd to the
    thing it's reporting on would be destroyed by the very delete it's meant
    to survive -- the same reason record_edit's history can't double as a
    deletion log (see edit.py). ``entity_id`` is likewise a plain int; the row
    it once pointed at is gone by the time this is read back."""

    __tablename__ = 'deletion_log'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    identifier_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)

    deleted_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True
    )
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    deleted_by: Mapped['UserDB | None'] = relationship('UserDB')

    __table_args__ = (Index('ix_deletion_log_paper_id', 'paper_id'),)


class DeletionLogResp(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    identifier_snapshot: str | None = None
    deleted_by_user_id: int | None = None
    deleted_by: UserSummaryResp | None = None
    deleted_at: UtcDatetime


def record_deletion(
    session: Session,
    *,
    paper_id: int,
    entity_type: str,
    entity_id: int,
    identifier_snapshot: str | None,
    editor: 'UserDB',
) -> None:
    """Append one deletion-log row. Call this before ``session.delete(obj)``,
    not after -- the snapshot has to be built from the row while it still
    exists.

    Flushes immediately, same reasoning as record_edit: a response built
    later in the same request must see this row rather than whatever happens
    to get flushed on the next unrelated query."""
    session.add(
        DeletionLogDB(
            paper_id=paper_id,
            entity_type=entity_type,
            entity_id=entity_id,
            identifier_snapshot=identifier_snapshot,
            deleted_by_user_id=editor.id,
            deleted_at=datetime.now(timezone.utc),
        )
    )
    session.flush()
