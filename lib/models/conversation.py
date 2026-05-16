from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from lib.models.base import Base


class ConversationDB(Base):
    """User conversation thread for a paper with OpenAI's Responses API.

    One conversation per paper (unique constraint on paper_id). Initialized on
    first user message by routing to the best matching extraction task. All
    subsequent messages in this conversation use that task's conversation_id
    from OpenAI's Responses API, ensuring context continuity.

    Design notes:
    - Single task per conversation for latency: avoids re-routing on each message
    - Users can interact with only one entity context per conversation
    - To chat about a different entity, users create a new paper conversation
    """

    __tablename__ = 'conversations'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('papers.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
        index=True,
    )
    conversation_id: Mapped[str] = mapped_column(String, nullable=False)
    messages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (UniqueConstraint('paper_id'),)


class ChatMessageRequest(BaseModel):
    message: str


class ChatMessageResp(BaseModel):
    response: str
