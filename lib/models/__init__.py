from enum import Enum

from pydantic import BaseModel
from sqlalchemy import (
    Column,
    String,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, declarative_base, mapped_column


class Base(DeclarativeBase):
    pass


class ExtractionStatus(str, Enum):
    EXTRACTED = 'EXTRACTED'
    FAILED = 'FAILED'
    QUEUED = 'QUEUED'


class PaperDB(Base):
    __tablename__ = 'jobs'

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        SQLEnum(ExtractionStatus),
        nullable=False,
        server_default=ExtractionStatus.QUEUED.value,
    )


class PaperResp(BaseModel):
    id: str
    filename: str
    extraction_status: ExtractionStatus
