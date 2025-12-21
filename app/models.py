from enum import Enum

from pydantic import BaseModel
from sqlalchemy import (
    Column,
    String,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ExtractionStatus(str, Enum):
    EXTRACTED = 'extracted'
    QUEUED = 'queued'
    FAILED = 'failed'


class PaperDB(Base):
    __tablename__ = 'jobs'

    id = Column(String, primary_key=True, index=True)
    status = Column(
        SQLEnum(ExtractionStatus),
        nullable=False,
        server_default=ExtractionStatus.QUEUED.value,
    )


class Paper(BaseModel):
    id: str
    status: ExtractionStatus


class PaperExtractionRequest(BaseModel):
    id: str
