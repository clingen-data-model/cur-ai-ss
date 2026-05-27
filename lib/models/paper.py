import hashlib
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, List

from pydantic import (
    BaseModel,
    computed_field,
    model_validator,
)

if TYPE_CHECKING:
    from lib.models.evidence_block import EvidenceBlock
    from lib.models.family import FamilyDB
    from lib.models.patient import PatientDB
    from lib.models.patient_variant_occurrences import (
        Inheritance,
        PatientVariantOccurrenceDB,
    )
    from lib.models.phenotype import PhenotypeDB
    from lib.models.variant import VariantDB
    from lib.tasks.models import TaskDB

from typing import Literal, TypeAlias

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)
from sqlalchemy.types import JSON
from typing_extensions import Self

from lib.core.environment import env
from lib.misc.pdf.paths import (
    pdf_highlighted_path,
    pdf_image_path,
    pdf_markdown_path,
    pdf_raw_path,
    pdf_sections_dir,
    pdf_tables_dir,
    pdf_thumbnail_path,
)
from lib.models.base import Base, PatchModel
from lib.models.evidence_block import EvidenceBlock
from lib.models.gene_disease_relation import GeneDiseaseRelation
from lib.models.patient_variant_occurrences import Inheritance
from lib.tasks.models import TaskResp

Color: TypeAlias = Literal[
    'red', 'orange', 'yellow', 'blue', 'green', 'violet', 'gray', 'grey', 'primary'
]


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


class PaperType(StrEnum):
    Letter = 'Letter'
    Research = 'Research'
    Case_series = 'Case Series'
    Case_study = 'Case Study'
    Cohort_analysis = 'Cohort Analysis'
    Case_control = 'Case Control'
    Unknown = 'Unknown'
    Other = 'Other'


class PaperTag(StrEnum):
    TrainingSet = 'TrainingSet'
    ValidationSet = 'ValidationSet'
    FailedPaperRelevancy = 'FailedPaperRelevancy'


class FileFormat(StrEnum):
    PDF = 'pdf'
    DOCX = 'docx'
    XLSX = 'xlsx'


class PaperDB(Base):
    __tablename__ = 'papers'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_hash: Mapped[str] = mapped_column(
        String,
        nullable=False,
        unique=True,
        index=True,
    )
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
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    supplement_format: Mapped[FileFormat | None] = mapped_column(
        SQLEnum(FileFormat),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Paper extraction metadata (populated asynchronously by extraction agent)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    first_author: Mapped[str | None] = mapped_column(String, nullable=True)
    journal_name: Mapped[str | None] = mapped_column(String, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    doi: Mapped[str | None] = mapped_column(String, nullable=True)
    pmid: Mapped[str | None] = mapped_column(String, nullable=True)
    pmcid: Mapped[str | None] = mapped_column(String, nullable=True)
    paper_types: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    tags: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    is_paper_relevant: Mapped[bool | None] = mapped_column(
        nullable=True,
    )
    section_classifications: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # Gene-disease relationship (extracted from paper text and case data)
    disease_name: Mapped[str | None] = mapped_column(String, nullable=True)
    disease_name_evidence: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )
    disease_inheritance_mode: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    disease_inheritance_mode_evidence: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )
    mondo_id: Mapped[str | None] = mapped_column(String, nullable=True)
    mondo_term: Mapped[str | None] = mapped_column(String, nullable=True)

    patient_count: int = 0
    variant_count: int = 0
    patient_variant_occurrences_count: int = 0

    @property
    def gene_symbol(self) -> str:
        return self.gene.symbol

    @classmethod
    def from_content(cls, content: bytes) -> 'PaperDB':
        h = hashlib.sha256()
        h.update(content)
        return cls(
            content_hash=h.hexdigest(),
        )

    def with_content(self) -> 'PaperDB':
        if not pdf_raw_path(self.id).exists():
            raise RuntimeError('Raw PDF must exist prior to calling this method')
        with open(pdf_raw_path(self.id), 'rb') as f:
            self.content = f.read()
        return self

    patients: Mapped[list['PatientDB']] = relationship(
        'PatientDB', back_populates='paper', cascade='all, delete-orphan'
    )
    families: Mapped[list['FamilyDB']] = relationship(
        'FamilyDB', back_populates='paper', cascade='all, delete-orphan'
    )
    pedigree: Mapped['PedigreeDB | None'] = relationship(
        'PedigreeDB',
        back_populates='paper',
        cascade='all, delete-orphan',
        uselist=False,
    )
    variants: Mapped[list['VariantDB']] = relationship(
        'VariantDB', back_populates='paper', cascade='all, delete-orphan'
    )
    patient_variant_occurrences: Mapped[list['PatientVariantOccurrenceDB']] = (
        relationship(
            'PatientVariantOccurrenceDB',
            back_populates='paper',
            cascade='all, delete-orphan',
        )
    )
    tasks: Mapped[list['TaskDB']] = relationship(
        'TaskDB', back_populates='paper', cascade='all, delete-orphan'
    )


class PaperExtractionOutput(BaseModel):
    title: str
    first_author: str
    journal_name: str | None
    abstract: str | None = None
    publication_year: int | None = None
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    paper_types: list[PaperType]
    gene_disease_relation: GeneDiseaseRelation | None = None

    @model_validator(mode='after')
    def max_two_paper_types(self) -> Self:
        if len(self.paper_types) > 2:
            raise ValueError('paper_types must contain at most two items')
        return self

    def apply_to(self, paper_db: PaperDB) -> None:
        data = self.model_dump()
        data['paper_types'] = [pt.value for pt in self.paper_types]
        gene_disease_relation = data.pop('gene_disease_relation', None)
        for key, value in data.items():
            setattr(paper_db, key, value)
        if gene_disease_relation is not None:
            paper_db.disease_name = gene_disease_relation['disease_name']['value']
            paper_db.disease_name_evidence = gene_disease_relation['disease_name']
            paper_db.disease_inheritance_mode = gene_disease_relation[
                'disease_inheritance_mode'
            ]['value']
            paper_db.disease_inheritance_mode_evidence = gene_disease_relation[
                'disease_inheritance_mode'
            ]


class PaperResp(PaperExtractionOutput):
    # From DB
    id: int
    content_hash: str
    gene_symbol: str
    filename: str
    tags: list[PaperTag] = []
    is_paper_relevant: bool | None = None
    section_classifications: dict | None = None
    disease_name: str | None = None
    disease_name_evidence: EvidenceBlock[str] | None = None
    disease_inheritance_mode: Inheritance | None = None
    disease_inheritance_mode_evidence: EvidenceBlock[Inheritance] | None = None
    mondo_id: str | None = None
    mondo_term: str | None = None
    updated_at: datetime
    tasks: list['TaskResp'] = []
    patient_count: int = 0
    variant_count: int = 0
    patient_variant_occurrences_count: int = 0

    # Override the PaperExtractionOutput to make the fields optional.
    # Note that mypy does not approve of the override, though Pydantic functions
    # just fine in practice.
    title: str | None = None  # type: ignore
    first_author: str | None = None  # type: ignore

    @computed_field  # type: ignore[misc]
    @property
    def thumbnail_url(self) -> str:
        from lib.misc.pdf.paths import pdf_thumbnail_path

        return str(pdf_thumbnail_path(self.id))

    @computed_field  # type: ignore[misc]
    @property
    def pdf_url(self) -> str:
        return str(pdf_raw_path(self.id))


class PaperUpdateRequest(PatchModel):
    title: str | None = None
    first_author: str | None = None
    journal_name: str | None = None
    abstract: str | None = None
    publication_year: int | None = None
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    paper_types: list[PaperType] | None = None
    tags: list[str] | None = None
    disease_name: str | None = None
    disease_inheritance_mode: Inheritance | None = None


class HighlightRequest(BaseModel):
    queries: list[str]
    image_ids: list[int]
    table_ids: list[int]
    color: str


class PedigreeDB(Base):
    __tablename__ = 'pedigrees'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('papers.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
    )
    image_id: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    paper: Mapped['PaperDB'] = relationship('PaperDB', back_populates='pedigree')

    __table_args__ = (
        UniqueConstraint('paper_id', 'image_id'),
        Index('ix_pedigrees_paper_id', 'paper_id'),
    )


class PedigreeResp(BaseModel):
    image_id: int
    description: str
