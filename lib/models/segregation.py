from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lib.models.base import Base, PatchModel

if TYPE_CHECKING:
    from lib.models.family import FamilyDB
    from lib.models.paper import PaperDB


class LodScoreType(StrEnum):
    Estimated = 'estimated'
    Published = 'published'


class SequencingMethodClass(StrEnum):
    CandidateGene = 'candidate_gene'
    ExomeGenome = 'exome_genome'


class FamilySegregationDB(Base):
    __tablename__ = 'family_segregations'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False
    )
    family_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('families.id', ondelete='CASCADE'), nullable=False
    )

    # Analysis fields
    inheritance_mode: Mapped[str | None] = mapped_column(String, nullable=True)
    sequencing_method_class: Mapped[str | None] = mapped_column(String, nullable=True)

    # Segregation counts
    n_affected_segregations: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    n_unaffected_segregations: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    # LOD score
    lod_score_type: Mapped[str | None] = mapped_column(String, nullable=True)
    lod_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    affected_risk: Mapped[float] = mapped_column(Float, nullable=False, default=0.25)

    # Inclusion and notes
    include_in_score: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    paper: Mapped['PaperDB'] = relationship('PaperDB')
    family: Mapped['FamilyDB'] = relationship('FamilyDB')

    __table_args__ = (
        UniqueConstraint(
            'paper_id',
            'family_id',
            name='uq_family_segregations_paper_family',
        ),
        Index('ix_family_segregations_paper_id', 'paper_id'),
    )


class FamilySegregationResp(BaseModel):
    id: int
    paper_id: int
    family_id: int
    family_identifier: str
    inheritance_mode: str | None
    sequencing_method_class: str | None
    n_affected_segregations: int
    n_unaffected_segregations: int
    lod_score_type: str | None
    lod_score: float | None
    affected_risk: float
    include_in_score: bool
    notes: str | None
    updated_at: datetime


class FamilySegregationUpdateRequest(PatchModel):
    inheritance_mode: str | None = None
    sequencing_method_class: str | None = None
    n_affected_segregations: int | None = None
    n_unaffected_segregations: int | None = None
    lod_score_type: str | None = None
    lod_score: float | None = None
    affected_risk: float | None = None
    include_in_score: bool | None = None
    notes: str | None = None

    def apply_to(self, obj: FamilySegregationDB) -> None:  # type: ignore[override]
        super().apply_to(obj)


class SegregationSummaryResp(BaseModel):
    paper_id: int
    total_lod: float
    candidate_lod: float
    exome_lod: float
    points: float
    family_count: int
    included_family_count: int
