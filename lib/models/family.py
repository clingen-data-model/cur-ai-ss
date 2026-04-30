from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from lib.models.base import Base, PatchModel
from lib.models.evidence_block import EvidenceBlock, HumanEvidenceBlock
from lib.models.paper import PaperDB

if TYPE_CHECKING:
    from lib.models.patient import PatientDB
    from lib.models.segregation_analysis import (
        SegregationAnalysisComputedDB,
        SegregationEvidenceDB,
    )


class Family(BaseModel):
    identifier: EvidenceBlock[str]


class FamilyDB(Base):
    __tablename__ = 'families'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False
    )
    identifier: Mapped[str] = mapped_column(String, nullable=False)
    identifier_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    paper: Mapped[PaperDB] = relationship('PaperDB', back_populates='families')
    patients: Mapped[list[PatientDB]] = relationship(
        'PatientDB', back_populates='family'
    )
    segregation_evidence: Mapped['SegregationEvidenceDB | None'] = relationship(
        'SegregationEvidenceDB', back_populates='family', cascade='all, delete-orphan'
    )
    segregation_analysis_computed: Mapped['SegregationAnalysisComputedDB | None'] = (
        relationship(
            'SegregationAnalysisComputedDB',
            back_populates='family',
            cascade='all, delete-orphan',
        )
    )

    __table_args__ = (Index('ix_families_paper_id', 'paper_id'),)


class FamilyResp(BaseModel):
    id: int
    paper_id: int
    identifier: str
    identifier_evidence: HumanEvidenceBlock[str]
    updated_at: datetime


class FamilyCreateRequest(BaseModel):
    identifier: str


class FamilyUpdateRequest(PatchModel):
    identifier: str | None = None
    identifier_human_edit_note: str | None = None

    def apply_to(self, obj: FamilyDB) -> None:  # type: ignore[override]
        super().apply_to(obj)
