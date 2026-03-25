from datetime import datetime
from enum import Enum
from typing import List

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
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON
from typing_extensions import Self

from lib.models.base import Base
from lib.models.evidence_block import EvidenceBlock


# ==============================
# Enums
# ==============================


class Zygosity(str, Enum):
    homozygous = 'homozygous'
    hemizygous = 'hemizygous'
    heterozygous = 'heterozygous'
    compound_heterozygous = 'compound heterozygous'
    unknown = 'unknown'


class Inheritance(str, Enum):
    dominant = 'dominant'
    recessive = 'recessive'
    semi_dominant = 'semi-dominant'
    x_linked = 'X-linked'
    de_novo = 'de novo'
    somatic_mosaicism = 'somatic mosaicism'
    mitochondrial = 'mitochondrial'
    unknown = 'unknown'


class TestingMethod(str, Enum):
    Chromosomal_microarray = 'Chromosomal_microarray'
    Next_generation_sequencing_panels = 'Next_generation_sequencing_panels'
    Exome_sequencing = 'Exome_sequencing'
    Genome_sequencing = 'Genome_sequencing'
    Sanger_sequencing = 'Sanger_sequencing'
    Pcr = 'PCR'
    Homozygosity_mapping = 'Homozygosity_mapping'
    Linkage_analysis = 'Linkage_analysis'
    Genotyping = 'Genotyping'
    Denaturing_gradient_gel = 'Denaturing_gradient_gel'
    High_resolution_melting = 'High_resolution_melting'
    Restriction_digest = 'Restriction_digest'
    Single_strand_conformation_polymorphism = 'Single_strand_conformation_polymorphism'
    Unknown = 'Unknown'
    Other = 'Other'


# ==============================
# Pydantic Models (Agent Input/Output)
# ==============================


class PatientVariantLink(BaseModel):
    patient_idx: int
    variant_idx: int
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
    paper_id: Mapped[str] = mapped_column(
        String, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False
    )
    patient_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    variant_idx: Mapped[int] = mapped_column(Integer, nullable=False)

    # Values (updateable)
    zygosity: Mapped[str] = mapped_column(String, nullable=False)
    inheritance: Mapped[str] = mapped_column(String, nullable=False)

    # Evidence blocks (static, JSON)
    zygosity_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    inheritance_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    testing_methods: Mapped[list] = mapped_column(JSON, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            'paper_id', 'patient_idx', 'variant_idx',
            name='uq_patient_variant_links_paper_patient_variant'
        ),
        Index('ix_patient_variant_links_paper_id', 'paper_id'),
    )


# ==============================
# Pydantic Response Model
# ==============================


class PatientVariantLinkResp(BaseModel):
    paper_id: str
    patient_idx: int
    variant_idx: int
    zygosity: Zygosity
    zygosity_evidence: EvidenceBlock[Zygosity]
    inheritance: Inheritance
    inheritance_evidence: EvidenceBlock[Inheritance]
    testing_methods: List[EvidenceBlock[TestingMethod]]
    updated_at: datetime
