"""A curator's additional context for a paper, one note per entry.

A paper's context is a list of notes rather than one text: each note keeps
where it came from (a re-run dialog, a flag's re-run, the chat agent), who
wrote it, when, and what it was about (``anchor``), so a curator can see the
list and remove a note that no longer holds, and so every agent can tell
which step or row an instruction is for. Every agent reads every note on
every run (``lib/tasks/context_notes.py`` renders them); a note stays until
a curator removes it.
"""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lib.models.base import Base
from lib.models.datetimes import UtcDatetime
from lib.models.user import UserSummaryResp

if TYPE_CHECKING:
    from lib.models.paper import PaperDB
    from lib.models.user import UserDB


class ContextNoteSource(StrEnum):
    # Typed into a re-run dialog (one task, all tasks, or a row's re-run).
    CURATOR = 'curator'
    # The note on a flag's re-run; keyed to the flag, so re-running the same
    # flag replaces it rather than adding a second.
    FLAG = 'flag'
    # Guidance the chat agent was given when it queued a task.
    CHAT = 'chat'


class PaperContextNoteDB(Base):
    __tablename__ = 'paper_context_notes'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('papers.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # ContextNoteSource's value. A plain string column, like flags.kind: a
    # String round-trips without the name-versus-value trap SQLEnum has (see
    # CLAUDE.md).
    source: Mapped[str] = mapped_column(String, nullable=False)
    # What the note was given for, as a label a reader knows it by: the step
    # and, for a row's re-run, the row ("Patient Demographics · patient P85"),
    # plus the flag's subject for a flag re-run. None for a note given to
    # every task. A label rather than foreign keys, so it outlives the flag
    # being resolved or the row being re-extracted.
    anchor: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The flag whose re-run made this note, for replacing it on the next
    # re-run of that flag. SET NULL: the note outlives the flag.
    flag_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('flags.id', ondelete='SET NULL'), nullable=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    paper: Mapped['PaperDB'] = relationship('PaperDB', back_populates='context_notes')
    created_by: Mapped['UserDB | None'] = relationship('UserDB')


class PaperContextNoteResp(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    source: ContextNoteSource
    anchor: str | None = None
    flag_id: int | None = None
    created_at: UtcDatetime
    created_by: UserSummaryResp | None = None
