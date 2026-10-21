from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lib.models.base import Base
from lib.models.datetimes import UtcDatetime
from lib.models.user import UserSummaryResp

if TYPE_CHECKING:
    from lib.models.paper import PaperDB
    from lib.models.user import UserDB


# TaskType member name -> the TaskDB column its handler reads (see
# TaskType.scope_column). Everything else runs over the whole paper.
_SCOPE_COLUMNS: dict[str, str] = {
    'PATIENT_DEMOGRAPHICS': 'patient_id',
    'PHENOTYPE_EXTRACTION': 'patient_id',
    'COMPOUND_HET_EVALUATION': 'patient_id',
    'SEGREGATION_EVIDENCE_EXTRACTION': 'family_id',
    'SEGREGATION_ANALYSIS_COMPUTED': 'family_id',
    'VARIANT_HARMONIZATION': 'variant_id',
    'VARIANT_ANNOTATION': 'variant_id',
    'HPO_LINKING': 'phenotype_id',
    'OCCURRENCE_MONDO_LINKING': 'patient_variant_occurrence_id',
}


class TaskType(StrEnum):
    """Pipeline task types in execution order."""

    PDF_PARSING = 'PDF Parsing'
    PAPER_CLASSIFIER = 'Paper Classifier'
    PAPER_METADATA = 'Paper Metadata'
    VARIANT_EXTRACTION = 'Variant Extraction'
    PEDIGREE_DESCRIPTION = 'Pedigree Description'
    PATIENT_EXTRACTION = 'Patient Extraction'
    PATIENT_DEMOGRAPHICS = 'Patient Demographics'  # per-patient

    SEGREGATION_EVIDENCE_EXTRACTION = 'Segregation Evidence Extraction'  # per-family
    SEGREGATION_ANALYSIS_COMPUTED = 'Segregation Analysis Computed'  # per-family
    VARIANT_HARMONIZATION = 'Variant Harmonization'
    VARIANT_ANNOTATION = 'Variant Annotation'
    PATIENT_VARIANT_OCCURRENCES = 'Patient Variant Occurrences'
    COMPOUND_HET_EVALUATION = 'Compound Het Evaluation'  # per-patient
    PHENOTYPE_EXTRACTION = 'Phenotype Extraction'  # per-patient
    HPO_LINKING = 'HPO Linking'  # per-patient
    # Two distinct types rather than one shared by both scopes: the paper-level
    # task is a single row, re-triggered (reset in place, not duplicated) by
    # either predecessor; the occurrence-level task fans out per occurrence,
    # atomically, from Patient Variant Occurrences alone. Kept separate so a
    # paper-level re-run can never look like the fan-out type's row count
    # jumping back up after it already read complete.
    PAPER_MONDO_LINKING = 'Paper MONDO Linking'
    OCCURRENCE_MONDO_LINKING = 'Occurrence MONDO Linking'  # per-occurrence
    # The pipeline's last step, one row per paper: a pass over everything the
    # other agents produced. Queued by the worker once every other task of
    # the paper has settled (see lib.bin.worker), not by an enqueue_successors
    # edge, because a paper settles on completions that take no successors
    # and on final failures too. Today it folds repeated flags into one
    # (lib.tasks.extraction_verification).
    EXTRACTION_VERIFICATION = 'Extraction Verification'

    @property
    def scope_column(self) -> str | None:
        """The TaskDB column this type's handler reads its one row from, or
        None for a type that runs over the whole paper. What a re-run of a
        single instance must set -- a task row scoped by any other column is
        a row the handler ignores and the queue never dedups against."""
        return _SCOPE_COLUMNS.get(self.name)

    @property
    def description(self) -> str:
        """One sentence on what this step is for: shown to curators in the Rerun
        Agent dialog (via GET /task-types) and listed for the chat agent."""
        descriptions: dict[TaskType, str] = {
            TaskType.PDF_PARSING: 'Reads the PDF into the text, tables and figures that every other step works from.',
            TaskType.PAPER_CLASSIFIER: 'Decides whether the paper has identifiable cases for this gene worth extracting; if not, the pipeline stops.',
            TaskType.PAPER_METADATA: 'Finds the title, authors, journal and year, and matches the paper to its PubMed record.',
            TaskType.VARIANT_EXTRACTION: 'Finds the genetic variants the paper reports, written as the paper writes them.',
            TaskType.PEDIGREE_DESCRIPTION: "Looks through the paper's figures for a family tree and describes the relationships and affected status it shows.",
            TaskType.PATIENT_EXTRACTION: 'Identifies each patient the paper describes, marks the probands and groups patients into families.',
            TaskType.PATIENT_DEMOGRAPHICS: "Fills in each patient's sex, ages, ancestry, affected status and relationship to the proband.",
            TaskType.SEGREGATION_EVIDENCE_EXTRACTION: 'Collects what the paper says about whether variants track with disease in each family, such as LOD scores.',
            TaskType.SEGREGATION_ANALYSIS_COMPUTED: 'Calculates segregation counts and points for each family from its extracted patients and variants.',
            TaskType.VARIANT_HARMONIZATION: 'Converts each variant to standard coordinates and identifiers (HGVS, rsID, ClinGen allele) using ClinVar, the Allele Registry and VariantValidator.',
            TaskType.VARIANT_ANNOTATION: 'Adds predictions and scores, such as SpliceAI, to each harmonized variant.',
            TaskType.PATIENT_VARIANT_OCCURRENCES: 'Links each patient to the variants they carry, with inheritance and testing details.',
            TaskType.COMPOUND_HET_EVALUATION: "Works out whether a patient's two variants sit on opposite copies of the gene (compound heterozygous).",
            TaskType.PHENOTYPE_EXTRACTION: "Pulls each patient's clinical features out of the text as the paper describes them.",
            TaskType.HPO_LINKING: "Matches each patient's clinical features to standard HPO terms.",
            TaskType.PAPER_MONDO_LINKING: "Matches the paper's disease name to a MONDO disease term.",
            TaskType.OCCURRENCE_MONDO_LINKING: 'Matches the disease named for a patient-variant pair to a MONDO disease term.',
            TaskType.EXTRACTION_VERIFICATION: 'Reviews the finished extraction and merges flags that raise the same decision more than once.',
        }
        return descriptions[self]


class TaskTypeResp(BaseModel):
    """GET /task-types: a pipeline step, what it is for, and the steps its
    completion queues (its TASK_SUCCESSORS edges), so the Rerun Agent dialog
    can show what else a re-run sets in motion."""

    type: TaskType
    description: str
    successors: list[TaskType]


class TaskStatus(StrEnum):
    PENDING = 'Pending'
    QUEUED = 'Queued'
    RUNNING = 'Running'
    COMPLETED = 'Completed'
    FAILED = 'Failed'


# The groupings of TaskStatus that matter, named because they overlap without
# coinciding and the difference is easy to get backwards.
#
# WAITING is what a user sees: the task is not executing. PENDING and QUEUED are
# both that. Their difference is the scheduler's bookkeeping -- QUEUED means it
# has claimed the row so it cannot schedule it twice (worker.py) -- and nothing
# a person is waiting on should be described by which side of that claim it
# happens to sit on.
WAITING_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.PENDING, TaskStatus.QUEUED}
)

# CLAIMED is what the scheduler sees: this row is spoken for, so do not re-queue
# it and do not delete it out from under a handler. QUEUED belongs with RUNNING
# here, and with PENDING above -- which is precisely why both names exist.
CLAIMED_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.QUEUED, TaskStatus.RUNNING}
)

# ACTIVE is everything short of a terminal status: work the paper is still
# owed. Display reads it as "something is happening here"; the reset paths read
# it as "data is still moving, do not overwrite it". Those are the same
# question, so they share the name rather than each spelling out the trio.
ACTIVE_STATUSES: frozenset[TaskStatus] = WAITING_STATUSES | {TaskStatus.RUNNING}


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
    TaskType.PDF_PARSING: [TaskType.PAPER_CLASSIFIER],
    TaskType.PAPER_CLASSIFIER: [
        TaskType.PAPER_METADATA,
        TaskType.VARIANT_EXTRACTION,
        TaskType.PEDIGREE_DESCRIPTION,
    ],
    TaskType.PEDIGREE_DESCRIPTION: [TaskType.PATIENT_EXTRACTION],
    # Occurrences hangs off patient *identity*, not demographics: its agent is
    # given each patient's id, identifier and citations and nothing
    # demographics fills in. Demographics used to sit between the two as an
    # ordering trick, which made a one-patient demographics re-run re-link
    # the whole paper. What demographics does feed -- affected status,
    # proband status, sex -- is read by the two segregation steps, so those
    # hang off it instead (gated below on every patient's run being in).
    TaskType.PATIENT_EXTRACTION: [
        TaskType.PATIENT_DEMOGRAPHICS,
        TaskType.PATIENT_VARIANT_OCCURRENCES,
    ],
    TaskType.PATIENT_DEMOGRAPHICS: [
        TaskType.PHENOTYPE_EXTRACTION,
        TaskType.SEGREGATION_EVIDENCE_EXTRACTION,
    ],
    TaskType.PAPER_METADATA: [TaskType.PAPER_MONDO_LINKING],
    TaskType.VARIANT_EXTRACTION: [
        TaskType.VARIANT_HARMONIZATION,
        TaskType.PATIENT_VARIANT_OCCURRENCES,
    ],
    TaskType.VARIANT_HARMONIZATION: [TaskType.VARIANT_ANNOTATION],
    TaskType.VARIANT_ANNOTATION: [TaskType.EXTRACTION_VERIFICATION],
    TaskType.PATIENT_VARIANT_OCCURRENCES: [
        # Fan-in with PATIENT_DEMOGRAPHICS: segregation reads the links and
        # the affected statuses, so whichever of the two finishes last
        # queues it (see enqueue_successors).
        TaskType.SEGREGATION_EVIDENCE_EXTRACTION,
        TaskType.COMPOUND_HET_EVALUATION,
        # Re-links the paper-level task (case-level occurrence extraction may
        # have updated paper.disease_name), and fans out the per-occurrence one.
        TaskType.PAPER_MONDO_LINKING,
        TaskType.OCCURRENCE_MONDO_LINKING,
    ],
    TaskType.SEGREGATION_EVIDENCE_EXTRACTION: [TaskType.SEGREGATION_ANALYSIS_COMPUTED],
    TaskType.SEGREGATION_ANALYSIS_COMPUTED: [TaskType.EXTRACTION_VERIFICATION],
    # One HPO_LINKING per phenotype the run produced that the HPO link cache
    # did not already link (enqueue_successors).
    TaskType.PHENOTYPE_EXTRACTION: [TaskType.HPO_LINKING],
    TaskType.HPO_LINKING: [TaskType.EXTRACTION_VERIFICATION],
    TaskType.PAPER_MONDO_LINKING: [TaskType.EXTRACTION_VERIFICATION],
    TaskType.OCCURRENCE_MONDO_LINKING: [TaskType.EXTRACTION_VERIFICATION],
    # Every leaf of the graph feeds verification. The edges are what make it
    # a descendant of everything -- so invalidate_descendants clears its row
    # on any re-run -- and what draws it last in the UI's DAG; the worker,
    # not enqueue_successors, is what queues it (see TaskType).
    TaskType.EXTRACTION_VERIFICATION: [],
}

# Pipeline leaves: task types with no successors. With verification fed by
# every other leaf, this is verification alone, so the completion snapshot
# and the owner's email follow the merged flags rather than precede them.
TERMINAL_TASK_TYPES: frozenset[TaskType] = frozenset(
    t for t in TaskType if not TASK_SUCCESSORS.get(t)
)


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

    # When the worker last moved this task to RUNNING. NULL until it does, and
    # re-stamped on a retry, so it always describes the attempt that produced
    # the current status.
    #
    # There is no matching finished_at: for a task in a terminal state,
    # updated_at already is the finish time, and nothing rewrites such a row
    # afterwards -- a re-run deletes the old rows rather than resetting them
    # (see invalidate_descendants). So duration is updated_at - started_at, and
    # only for COMPLETED or FAILED tasks; for a RUNNING one the pair measures
    # nothing, since updated_at is the moment it started.
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
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
    family_id: int | None
    patient_id: int | None
    variant_id: int | None
    phenotype_id: int | None
    patient_variant_occurrence_id: int | None
    started_at: UtcDatetime | None = None
    updated_at: UtcDatetime
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
    # A note to add to the paper's additional context (paper_context_notes),
    # the one place a curator's instructions go: every agent reads every note
    # on every run, and a note stays until a curator removes it. Blank adds
    # nothing. The note is anchored to this task type and, for a scoped run,
    # its row, so the agents can tell what it is for. There is no per-task
    # context -- a task used to get its own as a follow-up in its old
    # conversation, and a curator who picked the wrong task in the dialog
    # left the right agent unaware of it.
    additional_context: str | None = None


class RerunAllRequest(BaseModel):
    """Re-run every task of a paper, from the top of the pipeline."""

    # PDF parsing is not an agent and rebuilds the anchored text, tables and
    # images the agents cite, so re-parsing is a choice: without it the run
    # starts at the paper classifier, on the parse already on disk.
    reparse_pdf: bool = False
    # A note to add to the paper's additional context, as on
    # TaskCreateRequest, anchored to no step: it is for all of them.
    additional_context: str | None = None
