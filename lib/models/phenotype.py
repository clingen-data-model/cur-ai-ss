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
    patient_idx: int
    concept: EvidenceBlock[str]
    negated: bool = False
    uncertain: bool = False
    family_history: bool = False
    onset: str | None
    location: str | None
    severity: str | None
    modifier: str | None


class ExtractedPhenotypeOutput(BaseModel):
    extracted_phenotypes: List[ExtractedPhenotype]


class HpoCandidate(BaseModel):
    """HPO candidate suggestion from fuzzy matching."""

    hpo_id: str
    hpo_name: str
    similarity_score: float


class HPOTerm(BaseModel):
    """An HPO ontology term."""

    id: str
    name: str


class HpoLinkingEntry(BaseModel):
    """HPO linking result for a single phenotype."""

    phenotype_idx: int
    hpo: ReasoningBlock[HPOTerm | None]


class HpoLinkingOutput(BaseModel):
    """Output from the HPO linking agent."""

    links: List[HpoLinkingEntry]


class ExtractedPhenotypeDB(Base):
    __tablename__ = 'extracted_phenotypes'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[str] = mapped_column(
        String, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False
    )
    patient_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    phenotype_idx: Mapped[int] = mapped_column(Integer, nullable=False)

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

    paper: Mapped['PaperDB'] = relationship('PaperDB', overlaps='extracted_phenotypes')
    patient: Mapped['PatientDB'] = relationship(
        'PatientDB', back_populates='extracted_phenotypes', overlaps='paper'
    )
    hpo: Mapped['HpoDB | None'] = relationship(
        'HpoDB', back_populates='phenotype', uselist=False
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ['paper_id', 'patient_idx'],
            ['patients.paper_id', 'patients.patient_idx'],
            ondelete='CASCADE',
        ),
        UniqueConstraint(
            'paper_id',
            'patient_idx',
            'phenotype_idx',
            name='uq_extracted_phenotypes_paper_patient_phenotype_idx',
        ),
        Index('ix_extracted_phenotypes_paper_id', 'paper_id'),
        Index('ix_extracted_phenotypes_paper_patient', 'paper_id', 'patient_idx'),
    )


class HpoDB(Base):
    __tablename__ = 'hpos'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[str] = mapped_column(String, nullable=False)
    patient_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    phenotype_idx: Mapped[int] = mapped_column(Integer, nullable=False)

    hpo_term: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    hpo_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    phenotype: Mapped['ExtractedPhenotypeDB'] = relationship(
        'ExtractedPhenotypeDB', back_populates='hpo'
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ['paper_id', 'patient_idx', 'phenotype_idx'],
            [
                'extracted_phenotypes.paper_id',
                'extracted_phenotypes.patient_idx',
                'extracted_phenotypes.phenotype_idx',
            ],
            ondelete='CASCADE',
        ),
        UniqueConstraint(
            'paper_id',
            'patient_idx',
            'phenotype_idx',
            name='uq_hpos_paper_patient_phenotype',
        ),
        Index('ix_hpos_paper_id', 'paper_id'),
    )


class ExtractedPhenotypeResp(BaseModel):
    paper_id: str
    patient_idx: int
    phenotype_idx: int
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
    # HPO link (from hpos table, None if HPO linking not yet run)
    hpo: ReasoningBlock[HPOTerm | None] | None = None


class ExtractedPhenotypeUpdateRequest(PatchModel):
    negated: bool | None = None
    uncertain: bool | None = None
    family_history: bool | None = None
    onset: str | None = None
    location: str | None = None
    severity: str | None = None
    modifier: str | None = None
