from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from lib.models.base import Base


class AgentRunDB(Base):
    __tablename__ = 'agent_runs'

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    git_hash: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    model: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (Index('ix_agent_runs_updated_at', 'updated_at'),)


class AgentRunResp(BaseModel):
    id: int
    git_hash: str
    description: str | None
    model: str
    updated_at: datetime
