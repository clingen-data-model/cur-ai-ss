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
    EXTRACTED = 'EXTRACTED'
    FAILED = 'FAILED'
    QUEUED = 'QUEUED'


class PaperDB(Base):
    __tablename__ = 'jobs'

    id = Column(String, primary_key=True, index=True)
    filename = Column(String(255), nullable=False, index=True)
    status = Column(
        SQLEnum(ExtractionStatus),
        nullable=False,
        server_default=ExtractionStatus.QUEUED.value,
    )


class PaperResp(BaseModel):
    id: str
    filename: str
    status: ExtractionStatus
    thumbnail_path: str
