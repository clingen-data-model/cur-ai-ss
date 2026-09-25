from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List

from pydantic import BaseModel, model_validator
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
from typing_extensions import Self

from lib.models.base import Base, PatchModel
from lib.models.datetimes import UtcDatetime
from lib.models.evidence_block import (
    AttributedEvidenceBlock,
    AttributedReasoningBlock,
    EvidenceBlock,
    HumanEvidenceBlock,
    ReasoningBlock,
)
from lib.models.mondo import MondoComponentMapping, MondoTerm
from lib.models.user import UserSummaryResp

if TYPE_CHECKING:
    from lib.models.paper import PaperDB
    from lib.models.patient import PatientDB
    from lib.models.user import UserDB
    from lib.models.variant import VariantDB

# ==============================
# Enums
# ==============================


class Zygosity(str, Enum):
    homozygous = 'Homozygous'
    hemizygous = 'Hemizygous'
    heterozygous = 'Heterozygous'
    unknown = 'Unknown'


class Inheritance(str, Enum):
    dominant = 'Dominant'
    recessive = 'Recessive'
    semi_dominant = 'Semi-dominant'
    x_linked = 'X-linked'
    somatic_mosaicism = 'Somatic Mosaicism'
    mitochondrial = 'Mitochondrial'
    unknown = 'Unknown'


class TestingMethod(str, Enum):
    chromosomal_microarray = 'Chromosomal Microarray'
    next_generation_sequencing_panels = 'Next-generation Sequencing Panels'
    exome_sequencing = 'Exome Sequencing'
    genome_sequencing = 'Genome Sequencing'
    sanger_sequencing = 'Sanger Sequencing'
    pcr = 'PCR'
    homozygosity_mapping = 'Homozygosity Mapping'
    linkage_analysis = 'Linkage Analysis'
    genotyping = 'Genotyping'
    denaturing_gradient_gel = 'Denaturing Gradient Gel'
    high_resolution_melting = 'High-resolution Melting'
    restriction_digest = 'Restriction Digest'
    single_strand_conformation_polymorphism = 'Single-strand Conformation Polymorphism'
    unknown = 'Unknown'
    other = 'Other'


class CompoundHetConfidence(str, Enum):
    confirmed = 'confirmed'
    assumed = 'assumed'
    uncertain = 'uncertain'


# ==============================
# Pydantic Models (Agent Input/Output)
# ==============================


class PatientVariantOccurrence(BaseModel):
    patient_id: int
    variant_id: int
    zygosity: EvidenceBlock[Zygosity]
    inheritance: EvidenceBlock[Inheritance]
    de_novo: EvidenceBlock[bool]
    testing_methods: List[EvidenceBlock[TestingMethod]]
    disease_name: EvidenceBlock[str] | None = None

    @model_validator(mode='after')
    def max_two_methods(self) -> Self:
        if len(self.testing_methods) > 2:
            raise ValueError('testing_methods must contain at most two items')
        return self


class PatientVariantOccurrenceOutput(BaseModel):
    links: List[PatientVariantOccurrence]
    disease_name: EvidenceBlock[str] | None = None


class PatientVariantOccurrenceUpdateRequest(PatchModel):
    zygosity: Zygosity | None = None
    zygosity_human_edit_note: str | None = None
    inheritance: Inheritance | None = None
    inheritance_human_edit_note: str | None = None
    de_novo: bool | None = None
    de_novo_human_edit_note: str | None = None
    testing_methods: list[TestingMethod] | None = None
    testing_methods_note: str | None = None
    disease_name: str | None = None
    disease_name_human_edit_note: str | None = None

    @model_validator(mode='after')
    def max_two_methods(self) -> Self:
        if self.testing_methods is not None and len(self.testing_methods) > 2:
            raise ValueError('testing_methods must contain at most two items')
        return self


class PatientVariantOccurrenceCreateRequest(BaseModel):
    """Request to create a new patient-variant occurrence."""

    patient_id: int
    variant_id: int
    zygosity: Zygosity = Zygosity.unknown
    inheritance: Inheritance = Inheritance.unknown
    de_novo: bool = False
    testing_methods: list[TestingMethod] = []
    disease_name: str | None = None


class CompoundHetPair(BaseModel):
    variant_id_a: int
    variant_id_b: int
    confidence: ReasoningBlock[CompoundHetConfidence]


class CompoundHetEvaluationOutput(BaseModel):
    pairs: List[CompoundHetPair]


class OccurrencePairRequest(BaseModel):
    """Manually pair (or, with paired_occurrence_id=None, unpair) an
    occurrence with another occurrence of the same patient."""

    paired_occurrence_id: int | None


# ==============================
# SQLAlchemy DB Model
# ==============================


class PatientVariantOccurrenceDB(Base):
    __tablename__ = 'patient_variant_occurrences'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False
    )
    patient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('patients.id', ondelete='CASCADE'), nullable=False
    )
    variant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('variants.id', ondelete='CASCADE'), nullable=False
    )

    # Values (updateable)
    zygosity: Mapped[str] = mapped_column(String, nullable=False)
    inheritance: Mapped[str] = mapped_column(String, nullable=False)
    de_novo: Mapped[bool] = mapped_column(nullable=False)
    testing_methods: Mapped[list[str]] = mapped_column(JSON, nullable=False)

    # Evidence blocks (static, JSON)
    zygosity_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    inheritance_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    de_novo_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    testing_methods_evidence: Mapped[list] = mapped_column(JSON, nullable=False)
    # A single curator note covering both testing method slots - not per-item
    # attribution like HumanEvidenceBlock, since testing_methods_evidence is a
    # list rather than one block.
    testing_methods_note: Mapped[str | None] = mapped_column(String, nullable=True)
    disease_name: Mapped[str | None] = mapped_column(String, nullable=True)
    disease_name_evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    mondo_id: Mapped[str | None] = mapped_column(String, nullable=True)
    mondo_term: Mapped[str | None] = mapped_column(String, nullable=True)
    mondo_match_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    paired_variant_link_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('patient_variant_occurrences.id', ondelete='SET NULL'),
        nullable=True,
    )
    paired_variant_confidence: Mapped[str | None] = mapped_column(String, nullable=True)
    paired_variant_confidence_reasoning: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )

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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    # NULL means the extraction pipeline created this row -- see
    # PatientDB.created_by_user_id's comment for why this is a separate
    # column from updated_by_user_id.
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )

    paper: Mapped['PaperDB'] = relationship(
        'PaperDB', back_populates='patient_variant_occurrences'
    )
    patient: Mapped['PatientDB'] = relationship(
        'PatientDB', back_populates='patient_variant_occurrences'
    )
    variant: Mapped['VariantDB'] = relationship(
        'VariantDB', back_populates='patient_variant_occurrences'
    )
    updated_by: Mapped['UserDB | None'] = relationship(
        'UserDB', foreign_keys=[updated_by_user_id]
    )
    created_by: Mapped['UserDB | None'] = relationship(
        'UserDB', foreign_keys=[created_by_user_id]
    )
    paired_link: Mapped['PatientVariantOccurrenceDB | None'] = relationship(
        'PatientVariantOccurrenceDB',
        foreign_keys=[paired_variant_link_id],
        primaryjoin='PatientVariantOccurrenceDB.paired_variant_link_id == PatientVariantOccurrenceDB.id',
        uselist=False,
        remote_side='PatientVariantOccurrenceDB.id',
    )

    __table_args__ = (
        UniqueConstraint(
            'patient_id',
            'variant_id',
            name='uq_patient_variant_occurrences_patient_variant',
        ),
        Index('ix_patient_variant_occurrences_patient_id', 'patient_id'),
        Index('ix_patient_variant_occurrences_variant_id', 'variant_id'),
        Index(
            'ix_patient_variant_occurrences_paired_variant_link_id',
            'paired_variant_link_id',
        ),
    )


# ==============================
# Pydantic Response Model
# ==============================


class PatientVariantOccurrenceResp(BaseModel):
    id: int
    paper_id: int
    patient_id: int
    patient_identifier: str
    variant_id: int
    zygosity: Zygosity
    zygosity_evidence: HumanEvidenceBlock[Zygosity]
    inheritance: Inheritance
    inheritance_evidence: HumanEvidenceBlock[Inheritance]
    de_novo: bool
    de_novo_evidence: HumanEvidenceBlock[bool]
    testing_methods: list[TestingMethod]
    testing_methods_evidence: List[AttributedEvidenceBlock[TestingMethod]]
    testing_methods_note: str | None = None
    disease_name: str | None = None
    disease_name_evidence: HumanEvidenceBlock[str] | None = None
    mondo: ReasoningBlock[MondoTerm | None]
    mondo_components: list[MondoComponentMapping] = []
    paired_variant_link_id: int | None = None
    paired_variant_confidence: CompoundHetConfidence | None = None
    paired_variant_confidence_reasoning: (
        AttributedReasoningBlock[CompoundHetConfidence] | None
    ) = None
    updated_at: UtcDatetime
    updated_by_user_id: int | None = None
    updated_by: UserSummaryResp | None = None
    created_at: UtcDatetime
    created_by_user_id: int | None = None
    created_by: UserSummaryResp | None = None
