from enum import Enum

from pydantic import BaseModel
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declarative_base,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    pass


class ExtractionStatus(str, Enum):
    EXTRACTED = 'EXTRACTED'
    FAILED = 'FAILED'
    QUEUED = 'QUEUED'


class GeneDB(Base):
    __tablename__ = 'genes'

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    symbol: Mapped[str] = mapped_column(
        String,
        nullable=False,
        unique=True,
        index=True,
    )
    papers: Mapped[list['PaperDB']] = relationship(
        'PaperDB',
        back_populates='gene',
        cascade='all, delete-orphan',
    )

class GeneResp(BaseModel):
    id: int
    symbol: str

class PaperDB(Base):
    __tablename__ = 'papers'

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    gene_id: Mapped[str] = mapped_column(
        String,
        ForeignKey('genes.id', ondelete='CASCADE'),
        index=True,
        nullable=False,
    )
    gene: Mapped['GeneDB'] = relationship(
        'GeneDB',
        back_populates='papers',
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        SQLEnum(ExtractionStatus),
        nullable=False,
        server_default=ExtractionStatus.QUEUED.value,
    )

    @property
    def gene_symbol(self) -> str:
        return self.gene.symbol


class PaperResp(BaseModel):
    id: str
    gene_symbol: str
    filename: str
    extraction_status: ExtractionStatus
