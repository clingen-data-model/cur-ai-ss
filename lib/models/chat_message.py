from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lib.models.base import Base
from lib.models.datetimes import UtcDatetime
from lib.models.user import UserSummaryResp

if TYPE_CHECKING:
    from lib.models.paper import PaperDB
    from lib.models.user import UserDB


class ChatRole(StrEnum):
    USER = 'user'
    ASSISTANT = 'assistant'


class ProposalStatus(StrEnum):
    PENDING = 'pending'
    APPLIED = 'applied'
    CANCELLED = 'cancelled'


class ProposedCitation(BaseModel):
    anchor: str
    quote: str


class ProposedChange(BaseModel):
    """One field as the edit leaves it, for the confirmation card: its
    label, and the value before and after (None where there is none)."""

    field: str
    label: str
    old: str | None = None
    new: str | None = None


class EditEntity(StrEnum):
    """The rows a chat edit can change (named as the API names them, so an
    individual is a patient)."""

    FAMILY = 'family'
    PATIENT = 'patient'
    VARIANT = 'variant'
    OCCURRENCE = 'occurrence'
    PHENOTYPE = 'phenotype'


class EditAction(StrEnum):
    CREATE = 'create'
    UPDATE = 'update'
    DELETE = 'delete'


class ProposedEdit(BaseModel):
    """One direct edit the chat proposed, on any domain object: what it is,
    which row, how a curator knows it ("Seizures", for "Family 2 II-1"), the
    fields it changes and the quote it rests on -- everything the card shows,
    so it renders without a lookup. ``payload['request']`` is the request
    the paper page's form would send for this edit (a ``*CreateRequest`` or
    ``*UpdateRequest``, as JSON), which Apply hands to the function that
    form's endpoint calls; a phenotype create also carries ``patient_id``,
    which its endpoint takes from the path."""

    entity: EditEntity
    action: EditAction
    entity_id: int | None = None
    label: str
    owner_label: str | None = None
    changes: list[ProposedChange] = Field(default_factory=list)
    citation: ProposedCitation | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ChatProposal(BaseModel):
    """The direct edits a chat reply proposes. Nothing is written until the
    curator presses Apply, and then all of them or none. ``request`` is the
    curator's message, kept as the note on every edit it becomes; who applied
    or cancelled it is kept here, the edits themselves carrying their
    attribution in the edit history."""

    request: str = ''
    edits: list[ProposedEdit] = Field(default_factory=list)
    resolved_by_user_id: int | None = None
    resolved_by_name: str | None = None
    error: str | None = None


class ChatMessageDB(Base):
    """One row per chat message, scoped to a paper.

    One row per message (not the old feature's single JSON-blob ``messages``
    column) so the frontend's message-scroller can page and key off individual
    rows the way it expects a message list to be shaped.
    """

    __tablename__ = 'chat_messages'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False
    )
    role: Mapped[ChatRole] = mapped_column(SQLEnum(ChatRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Who sent a 'user' message; null for 'assistant' rows and for machine-sent ones.
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Direct edits this assistant reply proposes (ChatProposal), and whether
    # the curator applied or cancelled them. A plain String, not SQLEnum, so
    # the stored value is ProposalStatus's value (see CLAUDE.md on enums).
    proposal: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    proposal_status: Mapped[str | None] = mapped_column(String, nullable=True)
    proposal_resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    paper: Mapped['PaperDB'] = relationship('PaperDB', back_populates='chat_messages')
    created_by: Mapped['UserDB | None'] = relationship('UserDB')

    __table_args__ = (Index('ix_chat_messages_paper_id', 'paper_id'),)


class ChatMessageResp(BaseModel):
    id: int
    paper_id: int
    role: ChatRole
    content: str
    created_by_user_id: int | None = None
    created_by: UserSummaryResp | None = None
    created_at: UtcDatetime
    proposal: ChatProposal | None = None
    proposal_status: ProposalStatus | None = None
    proposal_resolved_at: UtcDatetime | None = None


class ChatMessageCreateRequest(BaseModel):
    message: str
