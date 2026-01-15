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


class CurationDB(Base):
    __tablename__ = 'curations'

    gene_symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    papers: Mapped[list['PaperDB']] = relationship(
        back_populates='gene',
        cascade='all, delete-orphan',
    )


class PaperDB(Base):
    __tablename__ = 'papers'

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    gene_symbol: Mapped[str] = mapped_column(
        String,
        ForeignKey('curations.gene_symbol', ondelete='CASCADE'),
        index=True,
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        SQLEnum(ExtractionStatus),
        nullable=False,
        server_default=ExtractionStatus.QUEUED.value,
    )


class PaperResp(BaseModel):
    id: str
    gene_symbol: str
    filename: str
    extraction_status: ExtractionStatus
