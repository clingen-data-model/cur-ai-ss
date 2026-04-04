from datetime import datetime
from typing import TYPE_CHECKING, List

from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from lib.models.base import Base, PatchModel
from lib.models.evidence_block import EvidenceBlock, ReasoningBlock

if TYPE_CHECKING:
    from lib.models.paper import PaperDB
    from lib.models.patient import PatientDB


class ExtractedPhenotype(BaseModel):
    patient_id: int
    concept: EvidenceBlock[str]
    negated: bool = False
    uncertain: bool = False
    family_history: bool = False
    onset: str | None
    location: str | None
    severity: str | None
    modifier: str | None


class HpoCandidate(BaseModel):
    """HPO candidate suggestion from fuzzy matching."""

    id: str
    name: str
    similarity_score: float


class HPOTerm(BaseModel):
    """An HPO ontology term."""

    id: str | None
    name: str | None


class PhenotypeDB(Base):
    __tablename__ = 'extracted_phenotypes'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False
    )
    patient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('patients.id', ondelete='CASCADE'), nullable=False
    )

    # Phenotype concept (value + evidence block)
    concept: Mapped[str] = mapped_column(String, nullable=False)
    concept_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)

    negated: Mapped[bool] = mapped_column(default=False, nullable=False)
    uncertain: Mapped[bool] = mapped_column(default=False, nullable=False)
    family_history: Mapped[bool] = mapped_column(default=False, nullable=False)
    onset: Mapped[str | None] = mapped_column(String, nullable=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    severity: Mapped[str | None] = mapped_column(String, nullable=True)
    modifier: Mapped[str | None] = mapped_column(String, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    paper: Mapped['PaperDB'] = relationship('PaperDB', overlaps='phenotypes')
    patient: Mapped['PatientDB'] = relationship(
        'PatientDB', back_populates='phenotypes', overlaps='paper'
    )
    hpo: Mapped['HpoDB | None'] = relationship(
        'HpoDB', back_populates='phenotype', uselist=False, cascade='all, delete-orphan'
    )

    __table_args__ = (
        Index('ix_extracted_phenotypes_paper_id', 'paper_id'),
        Index('ix_extracted_phenotypes_patient_id', 'patient_id'),
    )


class HpoDB(Base):
    __tablename__ = 'hpos'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phenotype_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('extracted_phenotypes.id', ondelete='CASCADE'),
        nullable=False,
    )

    hpo_id: Mapped[str | None] = mapped_column(String, nullable=True)
    hpo_name: Mapped[str | None] = mapped_column(String, nullable=True)
    reasoning: Mapped[str] = mapped_column(String, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    phenotype: Mapped['PhenotypeDB'] = relationship(
        'PhenotypeDB',
        back_populates='hpo',
        uselist=False,
    )

    __table_args__ = (
        UniqueConstraint(
            'phenotype_id',
            name='uq_hpos_phenotype_id',
        ),
    )


class PhenotypeResp(BaseModel):
    id: int
    paper_id: int
    patient_id: int
    concept: str
    negated: bool
    uncertain: bool
    family_history: bool
    onset: str | None
    location: str | None
    severity: str | None
    modifier: str | None
    updated_at: datetime
    # Evidence block (from DB JSON column)
    concept_evidence: EvidenceBlock[str]
    # HPO link (always present with ReasoningBlock, value may be None if not yet linked or excluded)
    hpo: ReasoningBlock[HPOTerm | None]


class PhenotypeUpdateRequest(PatchModel):
    negated: bool | None = None
    uncertain: bool | None = None
    family_history: bool | None = None
    onset: str | None = None
    location: str | None = None
    severity: str | None = None
    modifier: str | None = None
