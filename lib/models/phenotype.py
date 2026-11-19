from datetime import datetime
from typing import TYPE_CHECKING, List

from pydantic import BaseModel, ConfigDict, Field
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

from lib.models.base import Base
from lib.models.datetimes import UtcDatetime
from lib.models.evidence_block import (
    AttributedEvidenceBlock,
    AttributedReasoningBlock,
    EvidenceBlock,
)
from lib.models.flag import ExtractionFlag
from lib.models.signoff import SignoffColumns, SignoffFields

if TYPE_CHECKING:
    from lib.models.paper import PaperDB
    from lib.models.patient import PatientDB
    from lib.models.user import UserDB


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


class PhenotypeExtractionOutput(BaseModel):
    """Output from the patient phenotype linking agent: the phenotypes of the
    one patient it was run for, plus any flags (see lib.models.flag)."""

    phenotypes: List[ExtractedPhenotype]
    flags: List[ExtractionFlag] = Field(default_factory=list)


class HpoCandidate(BaseModel):
    """HPO candidate suggestion from fuzzy matching."""

    id: str
    name: str
    similarity_score: float


class HPOTerm(BaseModel):
    """An HPO ontology term."""

    id: str | None
    name: str | None


class PhenotypeDB(SignoffColumns, Base):
    """A phenotype of one individual, with its HPO link (``hpo``).

    ``reviewed_at``/``reviewed_by_user_id`` (SignoffColumns) say a curator
    accepted the term and its link in the HPO review. Relinking clears the
    stamp, since the term judged is gone; re-extraction recreates the rows.
    Unlike the occurrence stamp it does not move the paper's review status."""

    __tablename__ = 'phenotypes'

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
    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )

    paper: Mapped['PaperDB'] = relationship('PaperDB', overlaps='phenotypes')
    updated_by: Mapped['UserDB | None'] = relationship(
        'UserDB', foreign_keys='PhenotypeDB.updated_by_user_id'
    )
    patient: Mapped['PatientDB'] = relationship(
        'PatientDB', back_populates='phenotypes', overlaps='paper'
    )
    hpo: Mapped['HpoDB | None'] = relationship(
        'HpoDB', back_populates='phenotype', uselist=False, cascade='all, delete-orphan'
    )

    __table_args__ = (
        Index('ix_phenotypes_paper_id', 'paper_id'),
        Index('ix_phenotypes_patient_id', 'patient_id'),
    )


class HpoDB(Base):
    __tablename__ = 'hpos'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phenotype_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('phenotypes.id', ondelete='CASCADE'),
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


class PhenotypeResp(SignoffFields):
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
    updated_at: UtcDatetime
    updated_by_user_id: int | None = None
    # Evidence block (from DB JSON column)
    concept_evidence: AttributedEvidenceBlock[str]
    # HPO link (always present, value may be None if not yet linked or excluded)
    hpo: AttributedReasoningBlock[HPOTerm | None]


class PhenotypeCreateRequest(BaseModel):
    """Request to manually add a phenotype row for a patient. HPO id is
    optional; when given, the endpoint validates it against the ontology and
    looks up its canonical name."""

    concept: str
    hpo_id: str | None = None


class PhenotypeSignoffRequest(BaseModel):
    """Body for POST /papers/{paper_id}/phenotypes/signoff: the phenotypes to
    stamp as reviewed (or, with ``reviewed`` false, to unstamp)."""

    phenotype_ids: list[int] = []
    reviewed: bool = True


class HpoRelinkRequest(BaseModel):
    """Request to change which HPO term a phenotype is linked to, or clear
    the link entirely with hpo_id=None."""

    hpo_id: str | None
