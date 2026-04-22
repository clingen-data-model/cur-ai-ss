from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Float

from lib.models.base import Base, PatchModel
from lib.models.evidence_block import EvidenceBlock, HumanEvidenceBlock, ReasoningBlock

if TYPE_CHECKING:
    from lib.models.family import FamilyDB


class SequencingMethodology(str, Enum):
    CandidateGene = 'Candidate Gene'
    ExomeOrGenome = 'Exome/Genome'
    AllGenesInRegion = 'All Genes in Linkage Region'
    Unknown = 'Unknown'


# ============================================================================
# EVIDENCE EXTRACTION (from paper)
# ============================================================================


class SegregationEvidence(BaseModel):
    """Evidence extracted from paper by extraction agent."""

    family_id: int
    extracted_lod_score: EvidenceBlock[float] | None = None
    sequencing_methodology: EvidenceBlock[SequencingMethodology]
    has_unexplainable_non_segregations: EvidenceBlock[bool]


class SegregationEvidenceDB(Base):
    __tablename__ = 'segregation_evidence'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('families.id', ondelete='CASCADE'), nullable=False
    )

    # Extracted from paper
    extracted_lod_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    extracted_lod_score_evidence: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )

    sequencing_methodology: Mapped[str] = mapped_column(String, nullable=False)
    sequencing_methodology_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)

    has_unexplainable_non_segregations: Mapped[bool] = mapped_column(nullable=False)
    has_unexplainable_non_segregations_evidence: Mapped[dict] = mapped_column(
        JSON, nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    family: Mapped['FamilyDB'] = relationship(
        'FamilyDB', back_populates='segregation_evidence'
    )

    __table_args__ = (Index('ix_segregation_evidence_family_id', 'family_id'),)


class SegregationEvidenceResp(BaseModel):
    id: int
    family_id: int
    extracted_lod_score: HumanEvidenceBlock[float | None]
    sequencing_methodology: HumanEvidenceBlock[SequencingMethodology]
    has_unexplainable_non_segregations: HumanEvidenceBlock[bool]
    updated_at: datetime


class SegregationEvidenceUpdateRequest(PatchModel):
    """Update extracted evidence fields."""

    extracted_lod_score: float | None = None
    sequencing_methodology: str | None = None
    has_unexplainable_non_segregations: bool | None = None
    # Human edit notes
    extracted_lod_score_human_edit_note: str | None = None
    sequencing_methodology_human_edit_note: str | None = None
    has_unexplainable_non_segregations_human_edit_note: str | None = None


# ============================================================================
# COMPUTED ANALYSIS (from computation agent using family/patient/variant data)
# ============================================================================


class SegregationAnalysisComputed(BaseModel):
    """
    Computed segregation analysis values derived from family, patient, and
    variant data using ClinGen LOD score methodology.
    """

    family_id: int
    segregation_count: ReasoningBlock[int]
    computed_lod_score: ReasoningBlock[float]
    points_assigned: ReasoningBlock[float]
    meets_minimum_criteria: ReasoningBlock[bool]


class SegregationAnalysisComputedDB(Base):
    __tablename__ = 'segregation_analysis_computed'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('families.id', ondelete='CASCADE'), nullable=False
    )

    # Computed by agent from family/patient/variant data
    segregation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    segregation_count_reasoning: Mapped[dict] = mapped_column(JSON, nullable=False)

    computed_lod_score: Mapped[float] = mapped_column(Float, nullable=False)
    computed_lod_score_reasoning: Mapped[dict] = mapped_column(JSON, nullable=False)

    points_assigned: Mapped[float] = mapped_column(Float, nullable=False)
    points_assigned_reasoning: Mapped[dict] = mapped_column(JSON, nullable=False)

    meets_minimum_criteria: Mapped[bool] = mapped_column(nullable=False)
    meets_minimum_criteria_reasoning: Mapped[dict] = mapped_column(JSON, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    family: Mapped['FamilyDB'] = relationship(
        'FamilyDB', back_populates='segregation_analysis_computed'
    )

    __table_args__ = (Index('ix_segregation_analysis_computed_family_id', 'family_id'),)


class SegregationAnalysisComputedResp(BaseModel):
    id: int
    family_id: int
    segregation_count: ReasoningBlock[int]
    computed_lod_score: ReasoningBlock[float]
    points_assigned: ReasoningBlock[float]
    meets_minimum_criteria: ReasoningBlock[bool]
    updated_at: datetime


# ============================================================================
# COMBINED RESPONSE (for API)
# ============================================================================


class SegregationAnalysisComputedNestedResp(BaseModel):
    """Nested computed analysis results."""

    segregation_count: ReasoningBlock[int]
    computed_lod_score: ReasoningBlock[float]
    points_assigned: ReasoningBlock[float]
    meets_minimum_criteria: ReasoningBlock[bool]


class SegregationAnalysisResp(BaseModel):
    """Complete segregation analysis combining evidence + computed results."""

    id: int
    family_id: int
    # Evidence (from extraction agent)
    extracted_lod_score: HumanEvidenceBlock[float | None]
    sequencing_methodology: HumanEvidenceBlock[SequencingMethodology]
    has_unexplainable_non_segregations: HumanEvidenceBlock[bool]
    # Computed (from computation agent) - nested like harmonized/enriched variants
    computed: SegregationAnalysisComputedNestedResp | None = None
    updated_at: datetime


# ============================================================================
# AGENT OUTPUTS
# ============================================================================


class SegregationEvidenceExtractionOutput(BaseModel):
    """Output from segregation evidence extraction agent."""

    extracted_lod_score: EvidenceBlock[float | None]
    sequencing_methodology: EvidenceBlock[SequencingMethodology]
    has_unexplainable_non_segregations: EvidenceBlock[bool]


class SegregationAnalysisComputedOutput(BaseModel):
    """Output from segregation analysis computation agent."""

    segregation_count: ReasoningBlock[int]
    computed_lod_score: ReasoningBlock[float]
    points_assigned: ReasoningBlock[float]
    meets_minimum_criteria: ReasoningBlock[bool]
