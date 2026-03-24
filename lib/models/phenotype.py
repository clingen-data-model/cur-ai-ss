from datetime import datetime
from typing import TYPE_CHECKING, List

from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from lib.models.base import Base, PatchModel
from lib.models.evidence_block import EvidenceBlock

if TYPE_CHECKING:
    from lib.models.paper import PaperDB


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


class PhenotypeInfoExtractionOutput(BaseModel):
    extracted_phenotypes: List[ExtractedPhenotype]


class HpoPhenotypeLink(BaseModel):
    """Link between a phenotype and an HPO term."""

    patient_idx: int
    hpo_id: str | None
    hpo_name: str | None
    hpo_reasoning: str


class HpoPhenotypeLinkingOutput(BaseModel):
    """Output from HPO phenotype linking agent."""

    links: List[HpoPhenotypeLink]


class HpoCandidate(BaseModel):
    """HPO candidate suggestion from fuzzy matching."""

    hpo_id: str
    hpo_name: str
    similarity_score: float


class PhenotypeLinkingEntry(ExtractedPhenotype):
    """Combined phenotype extraction + HPO linking for one phenotype."""

    hpo_id: str | None = None
    hpo_name: str | None = None
    hpo_reasoning: str | None = None
    candidates: list[HpoCandidate] | None = None  # HPO candidate suggestions for agent

    @classmethod
    def from_extraction(
        cls,
        extraction: ExtractedPhenotype,
        hpo_id: str | None = None,
        hpo_name: str | None = None,
        hpo_reasoning: str | None = None,
        candidates: list[HpoCandidate] | None = None,
    ) -> 'PhenotypeLinkingEntry':
        """Create a PhenotypeLinkingEntry from a ExtractedPhenotype."""
        return cls(
            **extraction.model_dump(),
            hpo_id=hpo_id,
            hpo_name=hpo_name,
            hpo_reasoning=hpo_reasoning,
            candidates=candidates,
        )


class PhenotypeLinkingOutput(BaseModel):
    """Combined phenotype extraction + HPO linking output."""

    extracted_phenotypes: List[PhenotypeLinkingEntry]


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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    paper: Mapped['PaperDB'] = relationship(
        'PaperDB', back_populates='extracted_phenotypes'
    )

    __table_args__ = (
        UniqueConstraint(
            'paper_id',
            'patient_idx',
            'phenotype_idx',
            name='uq_extracted_phenotypes_paper_patient_phenotype_idx',
        ),
        Index('ix_extracted_phenotypes_paper_id', 'paper_id'),
        Index('ix_extracted_phenotypes_paper_patient', 'paper_id', 'patient_idx'),
    )


class ExtractedPhenotypeResp(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    created_at: datetime
    updated_at: datetime
    # Evidence block (from DB JSON column)
    concept_evidence: EvidenceBlock[str]


class ExtractedPhenotypeUpdateRequest(PatchModel):
    negated: bool | None = None
    uncertain: bool | None = None
    family_history: bool | None = None
    onset: str | None = None
    location: str | None = None
    severity: str | None = None
    modifier: str | None = None
