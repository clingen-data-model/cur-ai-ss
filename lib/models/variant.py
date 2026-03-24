from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel
from sqlalchemy import (
    Boolean,
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

from lib.models.base import Base
from lib.models.evidence_block import EvidenceBlock
from lib.models.paper import PaperDB


class VariantType(str, Enum):
    missense = 'missense'
    frameshift = 'frameshift'
    stop_gained = 'stop gained'
    splice_donor = 'splice donor'
    splice_acceptor = 'splice acceptor'
    splice_region = 'splice region'
    start_lost = 'start lost'
    inframe_deletion = 'inframe deletion'
    frameshift_deletion = 'frameshift deletion'
    inframe_insertion = 'inframe insertion'
    frameshift_insertion = 'frameshift insertion'
    structural = 'structural'
    synonymous = 'synonymous'
    intron = 'intron'
    five_utr = "5' UTR"
    three_utr = "3' UTR"
    non_coding = 'non-coding'
    unknown = 'unknown'


class GenomeBuild(str, Enum):
    GRCh37 = 'GRCh37'
    GRCh38 = 'GRCh38'


class ExtractedVariant(BaseModel):
    """ExtractedVariant extracted from paper by the extraction agent."""

    # Core extraction fields (gene comes from human, no evidence needed)
    gene: str

    # Variant-level evidence
    variant: EvidenceBlock[Optional[str]]

    # Reference sequences with evidence blocks
    transcript: EvidenceBlock[Optional[str]]
    protein_accession: EvidenceBlock[Optional[str]]
    genomic_accession: EvidenceBlock[Optional[str]]
    lrg_accession: EvidenceBlock[Optional[str]]
    gene_accession: EvidenceBlock[Optional[str]]
    genomic_coordinates: EvidenceBlock[Optional[str]]
    genome_build: EvidenceBlock[Optional[GenomeBuild]]
    rsid: EvidenceBlock[Optional[str]]
    caid: EvidenceBlock[Optional[str]]

    # HGVS with evidence blocks
    hgvs_c: EvidenceBlock[Optional[str]]
    hgvs_p: EvidenceBlock[Optional[str]]
    hgvs_g: EvidenceBlock[Optional[str]]

    # Variant type with evidence
    variant_type: EvidenceBlock[VariantType]

    # Functional evidence assessment with evidence block
    functional_evidence: EvidenceBlock[bool]


class VariantExtractionOutput(BaseModel):
    """Output from variant extraction agent."""

    variants: List[ExtractedVariant]


class ExtractedVariantResp(BaseModel):
    """Response model for extracted variants."""

    paper_id: str
    variant_idx: int
    gene: str
    transcript: Optional[str]
    protein_accession: Optional[str]
    genomic_accession: Optional[str]
    lrg_accession: Optional[str]
    gene_accession: Optional[str]
    genomic_coordinates: Optional[str]
    genome_build: Optional[str]
    rsid: Optional[str]
    caid: Optional[str]
    hgvs_c: Optional[str]
    hgvs_p: Optional[str]
    hgvs_g: Optional[str]
    variant_type: str
    functional_evidence: bool
    created_at: datetime
    # Evidence blocks (from DB JSON columns)
    transcript_evidence: EvidenceBlock[Optional[str]]
    protein_accession_evidence: EvidenceBlock[Optional[str]]
    genomic_accession_evidence: EvidenceBlock[Optional[str]]
    lrg_accession_evidence: EvidenceBlock[Optional[str]]
    gene_accession_evidence: EvidenceBlock[Optional[str]]
    genomic_coordinates_evidence: EvidenceBlock[Optional[str]]
    genome_build_evidence: EvidenceBlock[Optional[str]]
    rsid_evidence: EvidenceBlock[Optional[str]]
    caid_evidence: EvidenceBlock[Optional[str]]
    variant_evidence: EvidenceBlock[Optional[str]]
    hgvs_c_evidence: EvidenceBlock[Optional[str]]
    hgvs_p_evidence: EvidenceBlock[Optional[str]]
    hgvs_g_evidence: EvidenceBlock[Optional[str]]
    variant_type_evidence: EvidenceBlock[str]
    functional_evidence_evidence: EvidenceBlock[bool]


class ExtractedVariantDB(Base):
    __tablename__ = 'extracted_variants'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[str] = mapped_column(
        String, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False
    )
    variant_idx: Mapped[int] = mapped_column(Integer, nullable=False)

    # Core fields
    gene: Mapped[str] = mapped_column(String, nullable=False)
    transcript: Mapped[str | None] = mapped_column(String, nullable=True)
    protein_accession: Mapped[str | None] = mapped_column(String, nullable=True)
    genomic_accession: Mapped[str | None] = mapped_column(String, nullable=True)
    lrg_accession: Mapped[str | None] = mapped_column(String, nullable=True)
    gene_accession: Mapped[str | None] = mapped_column(String, nullable=True)
    genomic_coordinates: Mapped[str | None] = mapped_column(String, nullable=True)
    genome_build: Mapped[str | None] = mapped_column(String, nullable=True)
    rsid: Mapped[str | None] = mapped_column(String, nullable=True)
    caid: Mapped[str | None] = mapped_column(String, nullable=True)

    # HGVS
    hgvs_c: Mapped[str | None] = mapped_column(String, nullable=True)
    hgvs_p: Mapped[str | None] = mapped_column(String, nullable=True)
    hgvs_g: Mapped[str | None] = mapped_column(String, nullable=True)

    # Variant type
    variant_type: Mapped[str] = mapped_column(String, nullable=False)

    # Functional evidence
    functional_evidence: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Evidence blocks (static, immutable)
    transcript_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    protein_accession_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    genomic_accession_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    lrg_accession_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    gene_accession_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    genomic_coordinates_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    genome_build_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    rsid_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    caid_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    variant_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    hgvs_c_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    hgvs_p_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    hgvs_g_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    variant_type_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    functional_evidence_evidence: Mapped[dict] = mapped_column(JSON, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    paper: Mapped[PaperDB] = relationship(
        'PaperDB', back_populates='extracted_variants'
    )

    __table_args__ = (
        UniqueConstraint(
            'paper_id', 'variant_idx', name='uq_extracted_variants_paper_variant_idx'
        ),
        Index('ix_extracted_variants_paper_id', 'paper_id'),
    )
