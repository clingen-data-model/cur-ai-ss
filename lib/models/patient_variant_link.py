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
from lib.models.evidence_block import EvidenceBlock

if TYPE_CHECKING:
    from lib.models.paper import PaperDB

# ==============================
# Enums
# ==============================


class Zygosity(str, Enum):
    homozygous = 'Homozygous'
    hemizygous = 'Hemizygous'
    heterozygous = 'Heterozygous'
    compound_heterozygous = 'Compound Heterozygous'
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


# ==============================
# Pydantic Models (Agent Input/Output)
# ==============================


class PatientVariantLink(BaseModel):
    patient_id: int
    variant_id: int
    zygosity: EvidenceBlock[Zygosity]
    inheritance: EvidenceBlock[Inheritance]
    testing_methods: List[EvidenceBlock[TestingMethod]]

    @model_validator(mode='after')
    def max_two_methods(self) -> Self:
        if len(self.testing_methods) > 2:
            raise ValueError('testing_methods must contain at most two items')
        return self


class PatientVariantLinkerOutput(BaseModel):
    links: List[PatientVariantLink]


# ==============================
# SQLAlchemy DB Model
# ==============================


class PatientVariantLinkDB(Base):
    __tablename__ = 'patient_variant_links'

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
    testing_methods: Mapped[list[str]] = mapped_column(JSON, nullable=False)

    # Evidence blocks (static, JSON)
    zygosity_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    inheritance_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    testing_methods_evidence: Mapped[list] = mapped_column(JSON, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    paper: Mapped['PaperDB'] = relationship(
        'PaperDB', back_populates='patient_variant_links'
    )

    __table_args__ = (
        UniqueConstraint(
            'patient_id',
            'variant_id',
            name='uq_patient_variant_links_patient_variant',
        ),
        Index('ix_patient_variant_links_patient_id', 'patient_id'),
        Index('ix_patient_variant_links_variant_id', 'variant_id'),
    )


# ==============================
# Pydantic Response Model
# ==============================


class PatientVariantLinkResp(BaseModel):
    paper_id: int
    patient_id: int
    variant_id: int
    zygosity: Zygosity
    zygosity_evidence: EvidenceBlock[Zygosity]
    inheritance: Inheritance
    inheritance_evidence: EvidenceBlock[Inheritance]
    testing_methods: list[TestingMethod]
    testing_methods_evidence: List[EvidenceBlock[TestingMethod]]
    updated_at: datetime
