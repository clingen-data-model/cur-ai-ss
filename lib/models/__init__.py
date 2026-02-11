from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from pydantic import BaseModel
from sqlalchemy import (
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
    declarative_base,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    pass


class ExtractionStatus(str, Enum):
    PARSED = 'PARSED'
    FAILED = 'FAILED'
    QUEUED = 'QUEUED'


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


class StaticFileHeaderDB(Base):
    __tablename__ = 'static_file_headers'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_identifier: Mapped[str] = mapped_column(String, nullable=False, index=True)
    etag: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_modified: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    content_length: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now()
    )

    @classmethod
    def latest(
        cls, session: 'Session', identifier: str
    ) -> Optional['StaticFileHeaderDB']:
        """Return the most recent header record for the given file identifier."""
        from sqlalchemy import select

        stmt = (
            select(cls)
            .where(cls.file_identifier == identifier)
            .order_by(cls.created_at.desc())
            .limit(1)
        )
        return session.execute(stmt).scalar_one_or_none()

    def matches_headers(self, headers: dict[str, Optional[str]]) -> bool:
        """Check if cached headers match remote headers (ETag > Last-Modified > Content-Length)."""
        remote_etag = headers.get('etag')
        if self.etag and remote_etag:
            return self.etag == remote_etag

        remote_lm = headers.get('last_modified')
        if self.last_modified and remote_lm:
            return self.last_modified == remote_lm

        remote_cl = headers.get('content_length')
        if self.content_length and remote_cl:
            return self.content_length == remote_cl

        return False


class GeneResp(BaseModel):
    id: int
    symbol: str


class PaperDB(Base):
    __tablename__ = 'papers'

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    gene_id: Mapped[str] = mapped_column(
        String,
        ForeignKey('genes.id', ondelete='CASCADE'),
        index=True,
        nullable=False,
    )
    gene: Mapped['GeneDB'] = relationship(
        'GeneDB',
        back_populates='papers',
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        SQLEnum(ExtractionStatus),
        nullable=False,
        server_default=ExtractionStatus.QUEUED.value,
    )

    # --- Metadata columns (nullable, populated after NCBI fetch) ---
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

    # --- Relationships to extraction tables ---
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

    # Core patient fields
    identifier: Mapped[Optional[str]] = mapped_column(String, nullable=True)
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

    # Core extraction fields
    gene: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    transcript: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    variant_verbatim: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    genomic_coordinates: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Explicit HGVS from text
    hgvs_c: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    hgvs_p: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Optional inferred HGVS
    hgvs_c_inferred: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    hgvs_p_inferred: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    hgvs_inference_confidence: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    hgvs_inference_evidence_context: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )

    # Classification
    variant_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    zygosity: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    inheritance: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Evidence
    variant_type_evidence_context: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    variant_evidence_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    zygosity_evidence_context: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    inheritance_evidence_context: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )


# --- Pydantic response models ---


class PaperResp(BaseModel):
    id: str
    gene_symbol: str
    filename: str
    extraction_status: ExtractionStatus
    # Metadata fields (optional, populated after extraction)
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


class PatientResp(BaseModel):
    id: int
    paper_id: str
    identifier: Optional[str] = None
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
    gene: Optional[str] = None
    transcript: Optional[str] = None
    variant_verbatim: Optional[str] = None
    genomic_coordinates: Optional[str] = None
    hgvs_c: Optional[str] = None
    hgvs_p: Optional[str] = None
    hgvs_c_inferred: Optional[str] = None
    hgvs_p_inferred: Optional[str] = None
    hgvs_inference_confidence: Optional[str] = None
    hgvs_inference_evidence_context: Optional[str] = None
    variant_type: Optional[str] = None
    zygosity: Optional[str] = None
    inheritance: Optional[str] = None
    variant_type_evidence_context: Optional[str] = None
    variant_evidence_context: Optional[str] = None
    zygosity_evidence_context: Optional[str] = None
    inheritance_evidence_context: Optional[str] = None
