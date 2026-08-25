from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lib.models.base import Base
from lib.models.user import UserSummaryResp

if TYPE_CHECKING:
    from lib.models.agent_run import AgentRunDB
    from lib.models.paper import PaperDB
    from lib.models.user import UserDB


class TaskType(StrEnum):
    """Pipeline task types in execution order."""

    PDF_PARSING = 'PDF Parsing'
    GENERAL_PAPER_QUESTION = 'General Paper Question'
    PAPER_METADATA = 'Paper Metadata'

    SEGREGATION_ANALYSIS_COMPUTED = 'Segregation Analysis Computed'  # per-family
    VARIANT_HARMONIZATION = 'Variant Harmonization'
    VARIANT_ANNOTATION = 'Variant Annotation'
    HPO_LINKING = 'HPO Linking'  # per-patient
    MONDO_LINKING = 'MONDO Linking'

    # Reading the paper, split by entity. Each is one model call over the PDF
    # itself, so the queue can retry, rerun and time them separately.
    PEDIGREE_DESCRIPTION = 'Pedigree Description'
    PAPER_CLASSIFIER = 'Paper Classifier'
    PATIENT_EXTRACTION = 'Patient Extraction'
    VARIANT_EXTRACTION = 'Variant Extraction'
    PATIENT_DEMOGRAPHICS = 'Patient Demographics'
    PATIENT_VARIANT_OCCURRENCES = 'Patient Variant Occurrences'
    SEGREGATION_EVIDENCE_EXTRACTION = 'Segregation Evidence Extraction'

    @property
    def description(self) -> str:
        """Return a human-readable description with context about what this task does."""
        descriptions: dict[TaskType, str] = {
            TaskType.PDF_PARSING: 'Parses PDF file and extract text, tables, and images',
            TaskType.GENERAL_PAPER_QUESTION: 'Answers a general question using the full paper text and all extracted data',
            TaskType.PAPER_METADATA: 'Extracts paper title, authors, publication date, and other metadata; resolve to PubMed article',
            TaskType.SEGREGATION_ANALYSIS_COMPUTED: 'Computes segregation analysis results per family',
            TaskType.VARIANT_HARMONIZATION: 'Normalizes variants to standard genomic coordinates using ClinVar, dbSNP, ClinGen Allele Registry, and VariantValidator',
            TaskType.VARIANT_ANNOTATION: 'Adds annotations (SpliceAI, conservation scores, etc.) to variants',
            TaskType.HPO_LINKING: 'Maps phenotypes to HPO ontology terms for standardization',
            TaskType.MONDO_LINKING: 'Maps disease names to MONDO ontology terms for standardization',
            TaskType.PEDIGREE_DESCRIPTION: 'Finds which extracted figure is the pedigree and describes it individual by individual',
            TaskType.PAPER_CLASSIFIER: 'Reads the PDF for how the paper should be classified, whether it can be curated, and the disease it associates with the gene',
            TaskType.PATIENT_EXTRACTION: 'Reads the PDF for every individual it reports on, and how they group into families',
            TaskType.VARIANT_EXTRACTION: 'Reads the PDF for every variant it reports',
            TaskType.PATIENT_DEMOGRAPHICS: "Reads the PDF for each identified patient's demographics, ages and phenotypes",
            TaskType.PATIENT_VARIANT_OCCURRENCES: 'Reads the PDF for which patient carries which variant, and which variant pairs are in trans',
            TaskType.SEGREGATION_EVIDENCE_EXTRACTION: "Reads the PDF for each family's reported LOD score and non-segregations",
        }
        return descriptions[self]


class TaskStatus(StrEnum):
    PENDING = 'Pending'
    QUEUED = 'Queued'
    RUNNING = 'Running'
    COMPLETED = 'Completed'
    FAILED = 'Failed'


class InferredPaperStatus(StrEnum):
    """Inferred overall status of a paper based on its task states.

    This is a computed value, not a stored database value. It synthesizes
    the status of all tasks for a paper into a single status indicator.
    """

    PENDING = 'Pending'
    RUNNING = 'Running'
    FAILED = 'Failed'
    COMPLETED = 'Completed'


# Task dependencies: when a task completes, these become PENDING
TASK_SUCCESSORS: dict[TaskType, list[TaskType]] = {
    TaskType.PDF_PARSING: [
        TaskType.PAPER_CLASSIFIER,
        TaskType.PATIENT_EXTRACTION,
        TaskType.VARIANT_EXTRACTION,
        TaskType.PEDIGREE_DESCRIPTION,
        TaskType.PAPER_METADATA,
    ],
    # Classification writes paper-level fields and gates nothing.
    TaskType.PAPER_CLASSIFIER: [],
    # Nothing consumes the pedigree reading -- the passes read the figure out of
    # the PDF themselves -- so it is a leaf that runs for the UI's benefit
    # rather than a step the rest of the pipeline waits behind.
    TaskType.PEDIGREE_DESCRIPTION: [],
    # Patients and variants are what the later passes are keyed to. Genotypes
    # needs both, so it appears under each and enqueue_successors only queues it
    # once the other has landed -- whichever finishes second creates it.
    TaskType.PATIENT_EXTRACTION: [
        TaskType.PATIENT_DEMOGRAPHICS,
        TaskType.PATIENT_VARIANT_OCCURRENCES,
        TaskType.SEGREGATION_EVIDENCE_EXTRACTION,
    ],
    TaskType.VARIANT_EXTRACTION: [
        TaskType.PATIENT_VARIANT_OCCURRENCES,
        TaskType.VARIANT_HARMONIZATION,
    ],
    # Each reading pass now feeds only the lookups that need what it produced,
    # rather than every lookup waiting on every entity.
    TaskType.PATIENT_DEMOGRAPHICS: [TaskType.HPO_LINKING],
    TaskType.PATIENT_VARIANT_OCCURRENCES: [TaskType.MONDO_LINKING],
    TaskType.SEGREGATION_EVIDENCE_EXTRACTION: [TaskType.SEGREGATION_ANALYSIS_COMPUTED],
    TaskType.PAPER_METADATA: [TaskType.MONDO_LINKING],
    TaskType.VARIANT_HARMONIZATION: [TaskType.VARIANT_ANNOTATION],
    TaskType.VARIANT_ANNOTATION: [],
    TaskType.SEGREGATION_ANALYSIS_COMPUTED: [],
    TaskType.HPO_LINKING: [],
    TaskType.MONDO_LINKING: [],
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
    agent_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('agent_runs.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    paper: Mapped['PaperDB'] = relationship('PaperDB', back_populates='tasks')
    agent_run: Mapped['AgentRunDB'] = relationship('AgentRunDB')
    type: Mapped[TaskType] = mapped_column(
        SQLEnum(TaskType), nullable=False, index=True
    )
    family_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('families.id', ondelete='CASCADE'),
        nullable=True,
        index=True,
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
    patient_variant_occurrence_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('patient_variant_occurrences.id', ondelete='CASCADE'),
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
    skip_successors: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default='0'
    )
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    additional_context: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    # Which user triggered this task (null = machine-enqueued by the worker).
    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    updated_by: Mapped['UserDB | None'] = relationship('UserDB')

    __table_args__ = (
        Index('ix_tasks_paper_id_status', 'paper_id', 'status'),
        Index(
            'ix_tasks_dedup',
            'type',
            'paper_id',
            'family_id',
            'patient_id',
            'variant_id',
            'phenotype_id',
            'patient_variant_occurrence_id',
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
    skip_successors: bool
    conversation_id: str | None
    additional_context: str | None
    family_id: int | None
    patient_id: int | None
    variant_id: int | None
    phenotype_id: int | None
    patient_variant_occurrence_id: int | None
    updated_at: datetime
    updated_by_user_id: int | None = None
    updated_by: UserSummaryResp | None = None


class TaskCreateRequest(BaseModel):
    type: TaskType
    family_id: int | None = None
    patient_id: int | None = None
    variant_id: int | None = None
    phenotype_id: int | None = None
    patient_variant_occurrence_id: int | None = None
    skip_successors: bool = False
    additional_context: str | None = None
