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
    from lib.models.patient import PatientDB
    from lib.models.phenotype import ExtractedPhenotypeDB
    from lib.models.variant import ExtractedVariantDB

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

Color: TypeAlias = Literal[
    'red', 'orange', 'yellow', 'blue', 'green', 'violet', 'gray', 'grey', 'primary'
]


class PipelineStatus(StrEnum):
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


class PaperType(StrEnum):
    Letter = 'Letter'
    Research = 'Research'
    Case_series = 'Case_series'
    Case_study = 'Case_study'
    Cohort_analysis = 'Cohort_analysis'
    Case_control = 'Case_control'
    Unknown = 'Unknown'
    Other = 'Other'


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
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    pipeline_status: Mapped[PipelineStatus] = mapped_column(
        SQLEnum(PipelineStatus),
        nullable=False,
        server_default=PipelineStatus.QUEUED.value,
        index=True,
    )
    last_modified: Mapped[datetime] = mapped_column(
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

    @property
    def gene_symbol(self) -> str:
        return self.gene.symbol

    @classmethod
    def from_content(cls, content: bytes) -> 'PaperDB':
        h = hashlib.sha256()
        h.update(content)
        return cls(
            id=h.hexdigest(),
        )

    def with_content(self) -> 'PaperDB':
        if not pdf_raw_path(self.id).exists():
            raise RuntimeError('Raw PDF must exist prior to calling this method')
        with open(pdf_raw_path(self.id), 'rb') as f:
            self.content = f.read()
        return self

    @property
    def phenotype_linking_json_path(self) -> Path:
        return env.evagg_dir / self.id / 'phenotype_linking.json'

    @property
    def harmonized_variants_json_path(self) -> Path:
        return env.evagg_dir / self.id / 'harmonized_variants.json'

    @property
    def enriched_variants_json_path(self) -> Path:
        return env.evagg_dir / self.id / 'enriched_variants.json'

    @property
    def patient_variant_links_json_path(self) -> Path:
        return env.evagg_dir / self.id / 'patient_variant_links.json'

    patients: Mapped[list['PatientDB']] = relationship(
        'PatientDB', back_populates='paper', cascade='all, delete-orphan'
    )
    pedigree: Mapped['PedigreeDB | None'] = relationship(
        'PedigreeDB',
        back_populates='paper',
        cascade='all, delete-orphan',
        uselist=False,
    )
    extracted_variants: Mapped[list['ExtractedVariantDB']] = relationship(
        'ExtractedVariantDB', back_populates='paper', cascade='all, delete-orphan'
    )
    extracted_phenotypes: Mapped[list['ExtractedPhenotypeDB']] = relationship(
        'ExtractedPhenotypeDB', back_populates='paper', cascade='all, delete-orphan'
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

    @model_validator(mode='after')
    def max_two_paper_types(self) -> Self:
        if len(self.paper_types) > 2:
            raise ValueError('paper_types must contain at most two items')
        return self

    def apply_to(self, paper_db: PaperDB) -> None:
        data = self.model_dump()
        data['paper_types'] = [pt.value for pt in self.paper_types]
        for key, value in data.items():
            setattr(paper_db, key, value)


class PaperResp(PaperExtractionOutput):
    # From DB
    id: str
    gene_symbol: str
    filename: str
    pipeline_status: PipelineStatus
    last_modified: datetime

    # Override the PaperExtractionOutput to make the fields optional.
    # Handles the case when paper is QUEUED.
    # Note that mypy does not approve of the override, though Pydantic functions
    # just fine in practice.
    title: str | None = None  # type: ignore
    first_author: str | None = None  # type: ignore

    phenotype_linking_json_path: Path
    enriched_variants_json_path: Path
    harmonized_variants_json_path: Path
    patient_variant_links_json_path: Path

    @computed_field  # type: ignore
    @property
    def pdf_raw_path(self) -> Path:
        return pdf_raw_path(self.id)

    @computed_field  # type: ignore
    @property
    def pdf_thumbnail_path(self) -> Path:
        return pdf_thumbnail_path(self.id)

    @computed_field  # type: ignore
    @property
    def pdf_highlighted_path(self) -> Path:
        return pdf_highlighted_path(self.id)


class PaperUpdateRequest(PatchModel):
    pipeline_status: PipelineStatus | None = None
    title: str | None = None
    first_author: str | None = None
    journal_name: str | None = None
    abstract: str | None = None
    publication_year: int | None = None
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    paper_types: list[PaperType] | None = None
    prompt_override: str | None = None


class HighlightRequest(BaseModel):
    queries: list[str]
    image_ids: list[int]
    color: str


class PedigreeDB(Base):
    __tablename__ = 'pedigrees'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[str] = mapped_column(
        String, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False, unique=True
    )
    image_id: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    paper: Mapped['PaperDB'] = relationship('PaperDB', back_populates='pedigree')

    __table_args__ = (Index('ix_pedigrees_paper_id', 'paper_id'),)


class PedigreeResp(BaseModel):
    image_id: int
    description: str
