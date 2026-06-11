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

from lib.models.base import Base
from lib.models.evidence_block import EvidenceBlock, ReasoningBlock
from lib.reference_data.mondo import MondoTerm

if TYPE_CHECKING:
    from lib.models.paper import PaperDB
    from lib.models.patient import PatientDB
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
    de_novo = 'De Novo'
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


class CompoundHetPair(BaseModel):
    variant_id_a: int
    variant_id_b: int
    confidence: ReasoningBlock[CompoundHetConfidence]


class CompoundHetEvaluationOutput(BaseModel):
    pairs: List[CompoundHetPair]


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

    paper: Mapped['PaperDB'] = relationship(
        'PaperDB', back_populates='patient_variant_occurrences'
    )
    patient: Mapped['PatientDB'] = relationship(
        'PatientDB', back_populates='patient_variant_occurrences'
    )
    variant: Mapped['VariantDB'] = relationship(
        'VariantDB', back_populates='patient_variant_occurrences'
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
    zygosity_evidence: EvidenceBlock[Zygosity]
    inheritance: Inheritance
    inheritance_evidence: EvidenceBlock[Inheritance]
    de_novo: bool
    de_novo_evidence: EvidenceBlock[bool]
    testing_methods: list[TestingMethod]
    testing_methods_evidence: List[EvidenceBlock[TestingMethod]]
    disease_name: str | None = None
    disease_name_evidence: EvidenceBlock[str] | None = None
    mondo: ReasoningBlock[MondoTerm | None]
    paired_variant_link_id: int | None = None
    paired_variant_confidence: CompoundHetConfidence | None = None
    paired_variant_confidence_reasoning: (
        ReasoningBlock[CompoundHetConfidence] | None
    ) = None
    updated_at: datetime
