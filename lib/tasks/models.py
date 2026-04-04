from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lib.models.base import Base

if TYPE_CHECKING:
    from lib.models.paper import PaperDB


class TaskType(StrEnum):
    """Pipeline task types in execution order."""

    PDF_PARSING = 'PDF Parsing'
    PAPER_METADATA = 'Paper Metadata'
    VARIANT_EXTRACTION = 'Variant Extraction'
    PEDIGREE_DESCRIPTION = 'Pedigree Description'
    PATIENT_EXTRACTION = 'Patient Extraction'

    VARIANT_HARMONIZATION = 'Variant Harmonization'
    VARIANT_ENRICHMENT = 'Variant Enrichment'
    PATIENT_VARIANT_LINKING = 'Patient Variant Linking'
    PHENOTYPE_EXTRACTION = 'Phenotype Extraction'  # per-patient
    HPO_LINKING = 'HPO Linking'  # per-patient


class TaskStatus(StrEnum):
    PENDING = 'Pending'
    RUNNING = 'Running'
    COMPLETED = 'Completed'
    FAILED = 'Failed'


# Task dependencies: when a task completes, these become PENDING
TASK_SUCCESSORS: dict[TaskType, list[TaskType]] = {
    TaskType.PDF_PARSING: [
        TaskType.PAPER_METADATA,
        TaskType.VARIANT_EXTRACTION,
        TaskType.PEDIGREE_DESCRIPTION,
    ],
    TaskType.PEDIGREE_DESCRIPTION: [TaskType.PATIENT_EXTRACTION],
    TaskType.PATIENT_EXTRACTION: [
        TaskType.PHENOTYPE_EXTRACTION,
        TaskType.PATIENT_VARIANT_LINKING,
    ],
    TaskType.PAPER_METADATA: [],
    TaskType.VARIANT_EXTRACTION: [
        TaskType.VARIANT_HARMONIZATION,
        TaskType.PATIENT_VARIANT_LINKING,
    ],
    TaskType.VARIANT_HARMONIZATION: [TaskType.VARIANT_ENRICHMENT],
    TaskType.VARIANT_ENRICHMENT: [],
    TaskType.PATIENT_VARIANT_LINKING: [],
    TaskType.PHENOTYPE_EXTRACTION: [TaskType.HPO_LINKING],
    TaskType.HPO_LINKING: [],
}


class TaskDB(Base):
    __tablename__ = 'tasks'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('papers.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    paper: Mapped['PaperDB'] = relationship('PaperDB', back_populates='tasks')
    type: Mapped[TaskType] = mapped_column(
        SQLEnum(TaskType), nullable=False, index=True
    )
    patient_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('patients.id', ondelete='CASCADE'),
        nullable=True,
        index=True,
    )
    variant_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('variants.id', ondelete='CASCADE'),
        nullable=True,
        index=True,
    )
    phenotype_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('phenotypes.id', ondelete='CASCADE'),
        nullable=True,
        index=True,
    )
    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus),
        nullable=False,
        default=TaskStatus.PENDING.value,
        index=True,
    )
    tries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index('ix_tasks_paper_id_status', 'paper_id', 'status'),
        Index(
            'ix_tasks_dedup',
            'type',
            'paper_id',
            'patient_id',
            'variant_id',
            'phenotype_id',
            unique=True,
        ),
    )


class TaskResp(BaseModel):
    id: int
    paper_id: int
    type: TaskType
    status: TaskStatus
    tries: int
    error_message: str | None
    patient_id: int | None
    variant_id: int | None
    phenotype_id: int | None
    updated_at: datetime


class TaskCreateRequest(BaseModel):
    type: TaskType
    patient_id: int | None = None
    variant_id: int | None = None
    phenotype_id: int | None = None
