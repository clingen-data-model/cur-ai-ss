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
    file_name = Column(String(255), nullable=False, index=True)
    status = Column(
        SQLEnum(ExtractionStatus),
        nullable=False,
        server_default=ExtractionStatus.QUEUED.value,
    )


class Paper(BaseModel):
    id: str
    file_name: str
    status: ExtractionStatus


class PaperExtractionRequest(BaseModel):
    id: str
    file_name: str
