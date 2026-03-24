from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from lib.models.evidence_block import EvidenceBlock


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


class HgvsInferenceConfidence(str, Enum):
    high = 'high'
    medium = 'medium'
    low = 'low'


class GenomeBuild(str, Enum):
    GRCh37 = 'GRCh37'
    GRCh38 = 'GRCh38'


class Variant(BaseModel):
    """Variant extracted from paper by the extraction agent."""

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

    variants: List[Variant]


class ExtractedVariantResp(BaseModel):
    """Response model for extracted variants."""

    id: int
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
