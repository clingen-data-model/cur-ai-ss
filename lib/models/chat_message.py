from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
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


class ChatMessageCreateRequest(BaseModel):
    message: str
