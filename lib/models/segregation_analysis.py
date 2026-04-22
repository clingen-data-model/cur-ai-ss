from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Float

from lib.models.base import Base, PatchModel
from lib.models.evidence_block import EvidenceBlock, HumanEvidenceBlock

if TYPE_CHECKING:
    from lib.models.family import FamilyDB


class LODScoreType(str, Enum):
    Published = 'Published'
    Estimated = 'Estimated'


class SequencingMethodology(str, Enum):
    CandidateGene = 'Candidate Gene'
    ExomeOrGenome = 'Exome/Genome'
    AllGenesInRegion = 'All Genes in Linkage Region'
    Mixed = 'Mixed'
    Unknown = 'Unknown'


class SegregationAnalysis(BaseModel):
    """
    Segregation analysis for a family following ClinGen simplified LOD score methodology.

    Segregation analysis evaluates whether genetic variants co-segregate with disease
    in families. This model stores:
    - Segregation counts (affected individuals minus proband)
    - LOD scores (either published or estimated)
    - Sequencing methodology used to identify variants
    - Points assigned based on the ClinGen scoring matrix
    - Assessment of whether family meets criteria for LOD calculation
    """

    family_id: int
    segregation_count: EvidenceBlock[int]
    lod_score: EvidenceBlock[float]
    lod_score_type: EvidenceBlock[LODScoreType]
    sequencing_methodology: EvidenceBlock[SequencingMethodology]
    points_assigned: EvidenceBlock[float]
    meets_minimum_criteria: EvidenceBlock[bool] = Field(
        default_factory=lambda: EvidenceBlock(
            value=False, reasoning='Not yet evaluated'
        )
    )
    has_unexplainable_non_segregations: EvidenceBlock[bool] = Field(
        default_factory=lambda: EvidenceBlock(
            value=False, reasoning='No non-segregations identified'
        )
    )
    analysis_notes: str = Field(
        default='',
        description='Curator notes about the segregation analysis and LOD score calculation',
    )


class SegregationAnalysisDB(Base):
    __tablename__ = 'segregation_analyses'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('families.id', ondelete='CASCADE'), nullable=False
    )

    # Extracted values (updateable)
    segregation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    lod_score: Mapped[float] = mapped_column(Float, nullable=False)
    lod_score_type: Mapped[str] = mapped_column(String, nullable=False)
    sequencing_methodology: Mapped[str] = mapped_column(String, nullable=False)
    points_assigned: Mapped[float] = mapped_column(Float, nullable=False)
    meets_minimum_criteria: Mapped[bool] = mapped_column(default=False, nullable=False)
    has_unexplainable_non_segregations: Mapped[bool] = mapped_column(
        default=False, nullable=False
    )
    analysis_notes: Mapped[str] = mapped_column(default='', nullable=False)

    # Evidence blocks (static, JSON)
    segregation_count_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    lod_score_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    lod_score_type_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    sequencing_methodology_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    points_assigned_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    meets_minimum_criteria_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
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
        'FamilyDB', back_populates='segregation_analyses'
    )

    __table_args__ = (Index('ix_segregation_analyses_family_id', 'family_id'),)


class SegregationAnalysisResp(BaseModel):
    id: int
    family_id: int
    family_identifier: str
    segregation_count: int
    segregation_count_evidence: HumanEvidenceBlock[int]
    lod_score: float
    lod_score_evidence: HumanEvidenceBlock[float]
    lod_score_type: LODScoreType
    lod_score_type_evidence: HumanEvidenceBlock[LODScoreType]
    sequencing_methodology: SequencingMethodology
    sequencing_methodology_evidence: HumanEvidenceBlock[SequencingMethodology]
    points_assigned: float
    points_assigned_evidence: HumanEvidenceBlock[float]
    meets_minimum_criteria: bool
    meets_minimum_criteria_evidence: HumanEvidenceBlock[bool]
    has_unexplainable_non_segregations: bool
    has_unexplainable_non_segregations_evidence: HumanEvidenceBlock[bool]
    analysis_notes: str
    updated_at: datetime


class SegregationAnalysisCreateRequest(BaseModel):
    family_id: int
    segregation_count: int
    lod_score: float
    lod_score_type: str
    sequencing_methodology: str
    points_assigned: float
    meets_minimum_criteria: bool = False
    has_unexplainable_non_segregations: bool = False
    analysis_notes: str = ''


class SegregationAnalysisUpdateRequest(PatchModel):
    segregation_count: int | None = None
    lod_score: float | None = None
    lod_score_type: str | None = None
    sequencing_methodology: str | None = None
    points_assigned: float | None = None
    meets_minimum_criteria: bool | None = None
    has_unexplainable_non_segregations: bool | None = None
    analysis_notes: str | None = None
    # Human edit notes for evidence blocks
    segregation_count_human_edit_note: str | None = None
    lod_score_human_edit_note: str | None = None
    lod_score_type_human_edit_note: str | None = None
    sequencing_methodology_human_edit_note: str | None = None
    points_assigned_human_edit_note: str | None = None
    meets_minimum_criteria_human_edit_note: str | None = None
    has_unexplainable_non_segregations_human_edit_note: str | None = None
