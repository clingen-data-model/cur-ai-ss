import hashlib
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, field_validator
from sqlalchemy import (
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
from sqlalchemy.types import JSON

from lib.evagg.utils.environment import env

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
    pmid: Mapped[str | None] = mapped_column(String, nullable=True)
    pmcid: Mapped[str | None] = mapped_column(String, nullable=True)
    doi: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    journal_name: Mapped[str | None] = mapped_column(String, nullable=True)
    first_author: Mapped[str | None] = mapped_column(String, nullable=True)
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paper_types: Mapped[list | None] = mapped_column(JSON, nullable=True)

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

    @property
    def evagg_observations_path(self) -> Path:
        return env.evagg_dir / self.id / 'observations.json'

    @property
    def metadata_json_path(self) -> Path:
        return env.evagg_dir / self.id / 'metadata.json'

    @property
    def patient_info_json_path(self) -> Path:
        return env.evagg_dir / self.id / 'patient_info.json'

    @property
    def variants_json_path(self) -> Path:
        return env.evagg_dir / self.id / 'variants.json'

    @property
    def harmonized_variants_json_path(self) -> Path:
        return env.evagg_dir / self.id / 'harmonized_variants.json'

    @property
    def enriched_variants_json_path(self) -> Path:
        return env.evagg_dir / self.id / 'enriched_variants.json'

    @property
    def patient_variant_links_json_path(self) -> Path:
        return env.evagg_dir / self.id / 'patient_variant_links.json'

    @property
    def pdf_dir(self) -> Path:
        return env.extracted_pdf_dir / self.id

    @property
    def pdf_raw_path(self) -> Path:
        return self.pdf_dir / 'raw.pdf'

    @property
    def pdf_thumbnail_path(self) -> Path:
        return self.pdf_dir / 'thumbnail.png'

    @property
    def pdf_tables_dir(self) -> Path:
        return self.pdf_dir / 'tables'

    @property
    def pdf_images_dir(self) -> Path:
        return self.pdf_dir / 'images'

    @property
    def pdf_sections_dir(self) -> Path:
        return self.pdf_dir / 'sections'

    @property
    def pdf_markdown_path(self) -> Path:
        return self.pdf_dir / 'raw.md'

    @property
    def pdf_json_path(self) -> Path:
        return self.pdf_dir / 'raw.json'

    @property
    def pdf_words_json_path(self) -> Path:
        return self.pdf_dir / 'words.json'

    @property
    def pdf_extraction_success_path(self) -> Path:
        return self.pdf_dir / '_SUCCESS'

    def pdf_image_path(
        self,
        image_id: int,
    ) -> Path:
        return self.pdf_images_dir / f'{image_id}.png'

    def pdf_image_caption_path(
        self,
        image_id: int,
    ) -> Path:
        return self.pdf_images_dir / f'{image_id}.md'

    def pdf_table_image_path(
        self,
        table_id: int,
    ) -> Path:
        return self.pdf_tables_dir / f'{table_id}.png'

    def pdf_table_markdown_path(
        self,
        table_id: int,
    ) -> Path:
        return self.pdf_tables_dir / f'{table_id}.md'

    def pdf_section_markdown_path(
        self,
        section_id: int,
    ) -> Path:
        return self.pdf_sections_dir / f'{section_id}.md'


class PaperResp(BaseModel):
    id: str
    gene_symbol: str
    filename: str
    pipeline_status: PipelineStatus
    title: str | None
    first_author: str | None
    pdf_thumbnail_path: str

    @field_validator("pdf_thumbnail_path", mode="before")
    @classmethod
    def serialize_categories(cls, path):
        return str(path)

class PipelineUpdateRequest(BaseModel):
    pipeline_status: PipelineStatus
    prompt_override: str | None = None
