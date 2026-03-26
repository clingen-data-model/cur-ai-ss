from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
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
from lib.models.evidence_block import EvidenceBlock, ReasoningBlock
from lib.models.paper import PaperDB


class VariantType(str, Enum):
    missense = 'Missense'
    frameshift = 'Frameshift'
    stop_gained = 'Stop Gained'
    splice_donor = 'Splice Donor'
    splice_acceptor = 'Splice Acceptor'
    splice_region = 'Splice Region'
    start_lost = 'Start Lost'
    inframe_deletion = 'Inframe Deletion'
    frameshift_deletion = 'Frameshift Deletion'
    inframe_insertion = 'Inframe Insertion'
    frameshift_insertion = 'Frameshift Insertion'
    structural = 'Structural'
    synonymous = 'Synonymous'
    intron = 'Intron'
    five_utr = "5' UTR"
    three_utr = "3' UTR"
    non_coding = 'Non-Coding'
    unknown = 'Unknown'


class GenomeBuild(str, Enum):
    GRCh37 = 'GRCh37'
    GRCh38 = 'GRCh38'


class Variant(BaseModel):
    """Variant extracted from paper by the extraction agent."""

    # Variant-level evidence
    variant: ReasoningBlock[Optional[str]]

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
    functional_evidence: ReasoningBlock[bool]


class VariantExtractionOutput(BaseModel):
    """Output from variant extraction agent."""

    variants: List[Variant]


class HarmonizedVariant(BaseModel):
    """HarmonizedVariant output from the harmonization agent."""

    variant_id: int  # 1-based index matching input variant position
    gnomad_style_coordinates: Optional[str] = None
    rsid: Optional[str] = None
    caid: Optional[str] = None
    hgvs_c: Optional[str] = None
    hgvs_p: Optional[str] = None
    hgvs_g: Optional[str] = None
    reasoning: Optional[str] = None


class VariantHarmonizationOutput(BaseModel):
    """Output from variant harmonization agent."""

    variants: List[HarmonizedVariant]


class HarmonizedVariantResp(BaseModel):
    """Response model for harmonized variants."""

    gnomad_style_coordinates: Optional[str] = None
    rsid: Optional[str] = None
    caid: Optional[str] = None
    hgvs_c: Optional[str] = None
    hgvs_p: Optional[str] = None
    hgvs_g: Optional[str] = None
    reasoning: Optional[str] = None


class VariantResp(BaseModel):
    """Response model for extracted variants."""

    id: int
    paper_id: int
    variant: Optional[str]
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
    updated_at: datetime
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
    variant_evidence: ReasoningBlock[Optional[str]]
    hgvs_c_evidence: EvidenceBlock[Optional[str]]
    hgvs_p_evidence: EvidenceBlock[Optional[str]]
    hgvs_g_evidence: EvidenceBlock[Optional[str]]
    variant_type_evidence: EvidenceBlock[str]
    functional_evidence_evidence: ReasoningBlock[bool]
    # Harmonized variant (optional, may not yet be harmonized)
    harmonized_variant: Optional[HarmonizedVariantResp] = None
    # Enriched variant (optional, may not yet be enriched)
    enriched_variant: Optional['EnrichedVariantResp'] = None


class VariantDB(Base):
    __tablename__ = 'variants'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False
    )

    # Core fields
    variant: Mapped[str | None] = mapped_column(String, nullable=True)
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

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    paper: Mapped[PaperDB] = relationship('PaperDB', back_populates='variants')
    harmonized_variant: Mapped['HarmonizedVariantDB | None'] = relationship(
        'HarmonizedVariantDB', back_populates='variant', uselist=False
    )

    __table_args__ = (Index('ix_variants_paper_id', 'paper_id'),)


class HarmonizedVariantDB(Base):
    __tablename__ = 'harmonized_variants'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    variant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('variants.id', ondelete='CASCADE'), nullable=False
    )

    # Harmonized fields
    gnomad_style_coordinates: Mapped[str | None] = mapped_column(String, nullable=True)
    rsid: Mapped[str | None] = mapped_column(String, nullable=True)
    caid: Mapped[str | None] = mapped_column(String, nullable=True)
    hgvs_c: Mapped[str | None] = mapped_column(String, nullable=True)
    hgvs_p: Mapped[str | None] = mapped_column(String, nullable=True)
    hgvs_g: Mapped[str | None] = mapped_column(String, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(String, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    variant: Mapped['VariantDB'] = relationship(
        'VariantDB', back_populates='harmonized_variant', foreign_keys=[variant_id]
    )
    enriched_variant: Mapped['EnrichedVariantDB | None'] = relationship(
        'EnrichedVariantDB', back_populates='harmonized_variant', uselist=False
    )

    __table_args__ = (
        UniqueConstraint('variant_id', name='uq_harmonized_variants_variant_id'),
        Index('ix_harmonized_variants_variant_id', 'variant_id'),
    )


class SpliceAI(BaseModel):
    """SpliceAI prediction data from VEP."""

    max_score: float = 0.0
    effect_type: Optional[str] = None
    position: Optional[int] = None

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> 'SpliceAI':
        """Convert raw SpliceAI dict into max_score, effect_type, position."""
        ds_keys = ['DS_AG', 'DS_AL', 'DS_DG', 'DS_DL']
        dp_keys = ['DP_AG', 'DP_AL', 'DP_DG', 'DP_DL']

        max_score = 0.0
        effect_type = None
        position = None

        for ds, dp in zip(ds_keys, dp_keys):
            score = raw.get(ds, 0)
            if score > max_score:
                max_score = score
                effect_type = ds
                position = raw.get(dp)

        return cls(max_score=max_score, effect_type=effect_type, position=position)


class EnrichedVariant(BaseModel):
    """Enriched variant data from ClinVar, VEP, and gnomAD."""

    gnomad_style_coordinates: Optional[str] = None
    rsid: Optional[str] = None
    caid: Optional[str] = None
    pathogenicity: Optional[str] = None
    submissions: Optional[int] = None
    stars: Optional[int] = None
    exon: Optional[str] = None
    revel: Optional[float] = None
    alphamissense_class: Optional[str] = None
    alphamissense_score: Optional[float] = None
    spliceai: Optional[SpliceAI] = None

    # gnomAD
    gnomad_top_level_af: Optional[float] = None
    gnomad_popmax_af: Optional[float] = None
    gnomad_popmax_population: Optional[str] = None


class VariantEnrichmentOutput(BaseModel):
    """Output from variant enrichment agent."""

    variants: List[EnrichedVariant]


class EnrichedVariantResp(BaseModel):
    """Response model for enriched variants."""

    gnomad_style_coordinates: Optional[str] = None
    rsid: Optional[str] = None
    caid: Optional[str] = None
    pathogenicity: Optional[str] = None
    submissions: Optional[int] = None
    stars: Optional[int] = None
    exon: Optional[str] = None
    revel: Optional[float] = None
    alphamissense_class: Optional[str] = None
    alphamissense_score: Optional[float] = None
    spliceai: Optional[dict] = None  # Serialized SpliceAI

    gnomad_top_level_af: Optional[float] = None
    gnomad_popmax_af: Optional[float] = None
    gnomad_popmax_population: Optional[str] = None


class EnrichedVariantDB(Base):
    """Enriched variant data persisted to database."""

    __tablename__ = 'enriched_variants'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    harmonized_variant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('harmonized_variants.id', ondelete='CASCADE'),
        nullable=False,
    )

    # ClinVar
    pathogenicity: Mapped[str | None] = mapped_column(String, nullable=True)
    submissions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stars: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # VEP
    exon: Mapped[str | None] = mapped_column(String, nullable=True)
    revel: Mapped[float | None] = mapped_column(Float, nullable=True)
    alphamissense_class: Mapped[str | None] = mapped_column(String, nullable=True)
    alphamissense_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    spliceai: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Harmonized variant references
    gnomad_style_coordinates: Mapped[str | None] = mapped_column(String, nullable=True)
    rsid: Mapped[str | None] = mapped_column(String, nullable=True)
    caid: Mapped[str | None] = mapped_column(String, nullable=True)

    # gnomAD
    gnomad_top_level_af: Mapped[float | None] = mapped_column(Float, nullable=True)
    gnomad_popmax_af: Mapped[float | None] = mapped_column(Float, nullable=True)
    gnomad_popmax_population: Mapped[str | None] = mapped_column(String, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    harmonized_variant: Mapped[HarmonizedVariantDB] = relationship(
        'HarmonizedVariantDB',
        back_populates='enriched_variant',
        foreign_keys=[harmonized_variant_id],
    )

    __table_args__ = (
        UniqueConstraint(
            'harmonized_variant_id', name='uq_enriched_variants_harmonized_variant_id'
        ),
        Index('ix_enriched_variants_harmonized_variant_id', 'harmonized_variant_id'),
    )
