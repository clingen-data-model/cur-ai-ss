from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from lib.models.base import Base, PatchModel
from lib.models.evidence_block import EvidenceBlock, HumanEvidenceBlock
from lib.models.paper import PaperDB

if TYPE_CHECKING:
    from lib.models.agent_run import AgentRunDB
    from lib.models.patient import PatientDB
    from lib.models.segregation_analysis import (
        SegregationAnalysisComputedDB,
        SegregationEvidenceDB,
    )
    from lib.models.user import UserDB


class Family(BaseModel):
    identifier: EvidenceBlock[str]
    consanguinity: EvidenceBlock[bool]


class FamilyDB(Base):
    __tablename__ = 'families'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False
    )
    agent_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('agent_runs.id', ondelete='CASCADE'), nullable=False
    )
    identifier: Mapped[str] = mapped_column(String, nullable=False)
    identifier_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    consanguinity: Mapped[bool] = mapped_column(Boolean, nullable=False)
    consanguinity_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )

    paper: Mapped[PaperDB] = relationship('PaperDB', back_populates='families')
    updated_by: Mapped['UserDB | None'] = relationship('UserDB')
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

    __table_args__ = (
        Index('ix_families_paper_id', 'paper_id'),
        Index('ix_families_agent_run_id', 'agent_run_id'),
    )


class FamilyResp(BaseModel):
    id: int
    paper_id: int
    agent_run_id: int
    identifier: str
    identifier_evidence: HumanEvidenceBlock[str]
    consanguinity: bool
    consanguinity_evidence: HumanEvidenceBlock[bool]
    updated_at: datetime
    updated_by_user_id: int | None = None


class FamilyCreateRequest(BaseModel):
    identifier: str


class FamilyUpdateRequest(PatchModel):
    identifier: str | None = None
    identifier_human_edit_note: str | None = None
    consanguinity: bool | None = None
    consanguinity_human_edit_note: str | None = None

    def apply_to(  # type: ignore[override]
        self, obj: FamilyDB, updated_by_user_id: int | None = None
    ) -> None:
        super().apply_to(obj, updated_by_user_id)
