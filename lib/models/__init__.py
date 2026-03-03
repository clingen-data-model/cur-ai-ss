from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

Color = Literal[
    'red', 'orange', 'yellow', 'blue', 'green', 'violet', 'gray', 'grey', 'primary'
]


class Base(DeclarativeBase):
    pass


class PipelineStatus(str, Enum):
    QUEUED = 'Queued'

    EXTRACTION_RUNNING = 'Extraction Running...'
    EXTRACTION_FAILED = 'Extraction Failed'
    EXTRACTION_COMPLETED = 'Extraction Completed'

    LINKING_RUNNING = 'Linking Running...'
    LINKING_FAILED = 'Linking Failed'

    COMPLETED = 'Completed'

    @property
    def icon(self) -> str:
        return {
            PipelineStatus.QUEUED: '⏳',
            PipelineStatus.EXTRACTION_RUNNING: '🟡',
            PipelineStatus.EXTRACTION_FAILED: '❌',
            PipelineStatus.EXTRACTION_COMPLETED: '✔️',
            PipelineStatus.LINKING_RUNNING: '🟡',
            PipelineStatus.LINKING_FAILED: '❌',
            PipelineStatus.COMPLETED: '🎉',
        }[self]

    @property
    def color(self) -> Color:
        color_map: dict[PipelineStatus, Color] = {
            PipelineStatus.QUEUED: 'yellow',
            PipelineStatus.EXTRACTION_RUNNING: 'yellow',
            PipelineStatus.EXTRACTION_FAILED: 'red',
            PipelineStatus.EXTRACTION_COMPLETED: 'violet',
            PipelineStatus.LINKING_RUNNING: 'yellow',
            PipelineStatus.LINKING_FAILED: 'red',
            PipelineStatus.COMPLETED: 'green',
        }
        return color_map[self]


class GeneDB(Base):
    __tablename__ = 'genes'

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    symbol: Mapped[str] = mapped_column(
        String,
        nullable=False,
        unique=True,
        index=True,
    )
    papers: Mapped[list['PaperDB']] = relationship(
        'PaperDB',
        back_populates='gene',
        cascade='all, delete-orphan',
    )


class GeneResp(BaseModel):
    id: int
    symbol: str


class PaperDB(Base):
    __tablename__ = 'papers'

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    gene_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('genes.id', ondelete='CASCADE'),
        index=True,
        nullable=False,
    )
    gene: Mapped['GeneDB'] = relationship(
        'GeneDB',
        back_populates='papers',
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    pipeline_status: Mapped[PipelineStatus] = mapped_column(
        SQLEnum(PipelineStatus),
        nullable=False,
        server_default=PipelineStatus.QUEUED.value,
    )
    last_modified: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        index=True,
    )

    # Paper metadata (nullable, populated after extraction)
    pmid: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pmcid: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    doi: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    journal: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    first_author: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pub_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    citation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_open_access: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    can_access: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    license: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    link: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Metadata fields stored as JSON arrays
    paper_types: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    testing_methods: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    testing_methods_evidence: Mapped[Optional[list[Optional[str]]]] = mapped_column(
        JSON, nullable=True
    )

    # Relationships
    patients: Mapped[list['PatientDB']] = relationship(
        'PatientDB',
        back_populates='paper',
        cascade='all, delete-orphan',
    )
    variants: Mapped[list['VariantDB']] = relationship(
        'VariantDB',
        back_populates='paper',
        cascade='all, delete-orphan',
    )

    @property
    def gene_symbol(self) -> str:
        return self.gene.symbol


class PatientDB(Base):
    __tablename__ = 'patients'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[str] = mapped_column(
        String,
        ForeignKey('papers.id', ondelete='CASCADE'),
        index=True,
        nullable=False,
    )
    paper: Mapped['PaperDB'] = relationship('PaperDB', back_populates='patients')

    # Core fields
    identifier: Mapped[str] = mapped_column(String, nullable=False)
    proband_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sex: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    age_diagnosis: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    age_report: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    age_death: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    country_of_origin: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    race_ethnicity: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Evidence fields
    identifier_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sex_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    age_diagnosis_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    age_report_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    age_death_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    country_of_origin_evidence: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    race_ethnicity_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class VariantDB(Base):
    __tablename__ = 'variants'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[str] = mapped_column(
        String,
        ForeignKey('papers.id', ondelete='CASCADE'),
        index=True,
        nullable=False,
    )
    paper: Mapped['PaperDB'] = relationship('PaperDB', back_populates='variants')

    # Core fields
    gene: Mapped[str] = mapped_column(String, nullable=False)
    transcript: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    protein_accession: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    genomic_accession: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    lrg_accession: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    gene_accession: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    variant_description_verbatim: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    genomic_coordinates: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    genome_build: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rsid: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    caid: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Explicit HGVS
    hgvs_c: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    hgvs_p: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    hgvs_g: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Inferred HGVS
    hgvs_c_inferred: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    hgvs_p_inferred: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    hgvs_p_inference_confidence: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    hgvs_p_inference_evidence_context: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    hgvs_c_inference_confidence: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    hgvs_c_inference_evidence_context: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )

    variant_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Evidence
    variant_evidence_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    variant_type_evidence_context: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )


class PaperResp(BaseModel):
    id: str
    gene_symbol: str
    filename: str
    pipeline_status: PipelineStatus

    # Optional metadata fields
    pmid: Optional[str] = None
    pmcid: Optional[str] = None
    doi: Optional[str] = None
    title: Optional[str] = None
    abstract: Optional[str] = None
    journal: Optional[str] = None
    first_author: Optional[str] = None
    pub_year: Optional[int] = None
    citation: Optional[str] = None
    is_open_access: Optional[bool] = None
    can_access: Optional[bool] = None
    license: Optional[str] = None
    link: Optional[str] = None
    paper_types: Optional[list[str]] = None
    testing_methods: Optional[list[str]] = None
    testing_methods_evidence: Optional[list[Optional[str]]] = None


class PatientResp(BaseModel):
    id: int
    paper_id: str
    identifier: str
    proband_status: Optional[str] = None
    sex: Optional[str] = None
    age_diagnosis: Optional[str] = None
    age_report: Optional[str] = None
    age_death: Optional[str] = None
    country_of_origin: Optional[str] = None
    race_ethnicity: Optional[str] = None
    identifier_evidence: Optional[str] = None
    sex_evidence: Optional[str] = None
    age_diagnosis_evidence: Optional[str] = None
    age_report_evidence: Optional[str] = None
    age_death_evidence: Optional[str] = None
    country_of_origin_evidence: Optional[str] = None
    race_ethnicity_evidence: Optional[str] = None


class VariantResp(BaseModel):
    id: int
    paper_id: str
    gene: str
    transcript: Optional[str] = None
    protein_accession: Optional[str] = None
    genomic_accession: Optional[str] = None
    lrg_accession: Optional[str] = None
    gene_accession: Optional[str] = None
    variant_description_verbatim: Optional[str] = None
    genomic_coordinates: Optional[str] = None
    genome_build: Optional[str] = None
    rsid: Optional[str] = None
    caid: Optional[str] = None
    hgvs_c: Optional[str] = None
    hgvs_p: Optional[str] = None
    hgvs_g: Optional[str] = None
    hgvs_c_inferred: Optional[str] = None
    hgvs_p_inferred: Optional[str] = None
    hgvs_p_inference_confidence: Optional[str] = None
    hgvs_p_inference_evidence_context: Optional[str] = None
    hgvs_c_inference_confidence: Optional[str] = None
    hgvs_c_inference_evidence_context: Optional[str] = None
    variant_type: Optional[str] = None
    variant_evidence_context: Optional[str] = None
    variant_type_evidence_context: Optional[str] = None


class PipelineUpdateRequest(BaseModel):
    pipeline_status: PipelineStatus
    prompt_override: str | None = None
