"""Curator flags: a decision an agent made that a curator should look at.

Every extracted value already carries its reasoning, so a flag is not another
copy of that. It exists for the two things a field's reasoning cannot carry:

- a decision about something that was *not* extracted (a candidate the agent
  rejected under a scoping rule, a relative mentioned once without a stated
  fact, a variant left out for having no structured identifier), which has no
  row to hang on; and
- a decision that *was* extracted but turned on a judgment call the paper
  itself leaves open (no proband marked, text and table disagree, a zygosity
  read off a pedigree symbol).

Any extraction agent can raise one; the shared rule is the FLAGS section of
``CORE_EXTRACTION_SPEC``. The row is deliberately thin: who raised it, which
extracted rows it is about (any of family, patient, variant, phenotype -- a
flag about a patient's phenotype carries both), the agent's evidence block
(reasoning plus citations, the same shape as every ``*_evidence`` column so
the UI renders it the same way), and who resolved it.
"""

from datetime import datetime
from typing import TYPE_CHECKING, ClassVar, Generic, TypeVar

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from lib.models.base import Base
from lib.models.datetimes import UtcDatetime
from lib.models.evidence_block import EvidenceBlock, HumanEvidenceBlock, ReasoningBlock
from lib.models.user import UserSummaryResp

if TYPE_CHECKING:
    from lib.models.family import FamilyDB
    from lib.models.paper import PaperDB
    from lib.models.patient import PatientDB
    from lib.models.patient_variant_occurrences import PatientVariantOccurrenceDB
    from lib.models.phenotype import PhenotypeDB
    from lib.models.user import UserDB
    from lib.models.variant import VariantDB


class FlagEvidenceBlock(EvidenceBlock[str]):
    """A flag's evidence: cited where the paper says something, and allowed
    to cite nothing where it does not. The common flag is about an absence
    (the target gene never mentioned, a relative never described), and an
    absence has no block to quote. The value is the flag's subject, which
    EvidenceBlock's "Unknown"/False exemptions never match, so the base
    requirement would reject exactly those flags and fail the whole output
    (seen on the first local run: an ITPR3 paper uploaded under MASP1)."""

    require_source: ClassVar[bool] = False


class ExtractionFlag(BaseModel):
    """One flag as an agent returns it, in any agent's output.

    ``about`` names the extracted thing the flag concerns, exactly as it
    appears in the agent's own output or in the input it was given -- a
    patient or family identifier, a variant as written, a phenotype concept --
    or is null when the flag is about something that was not extracted, which
    is the point of a flag and so the common case. The handler resolves it to
    the row it just wrote; an ``about`` it cannot match is kept in the subject
    and reasoning, not lost. ``flag.value`` is a short subject; the reasoning
    says what was decided and why; the citations point at the text it rests
    on, when there is any.
    """

    about: str | None
    flag: FlagEvidenceBlock


class ReasoningFlag(BaseModel):
    """The same flag from an agent that works from lookups and structured
    input rather than the paper's text (harmonization, HPO and MONDO linking,
    the computed segregation analysis, compound-het phasing): there is no
    block to cite, so the flag is a reasoning block."""

    about: str | None
    flag: ReasoningBlock[str]


T = TypeVar('T')


class FlaggedReasoningBlock(ReasoningBlock[T], Generic[T]):
    """A ReasoningBlock output with a flags list beside it, for the agents
    whose whole output is one block (a harmonized variant, an HPO term, a
    MONDO decision). Handlers keep reading ``value`` and ``reasoning``."""

    flags: list[ReasoningFlag] = Field(default_factory=list)


AnyFlag = ExtractionFlag | ReasoningFlag

# The link columns a resolved ``about`` (or a task's own scope) can fill.
LINK_COLUMNS = (
    'family_id',
    'patient_id',
    'variant_id',
    'occurrence_id',
    'paired_occurrence_id',
    'phenotype_id',
)


class FlagDB(Base):
    __tablename__ = 'flags'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False
    )
    # The extracted rows the flag is about, when there are any. Not an
    # exclusive arc: a flag about one of a patient's phenotypes carries both
    # ids, so it lists under the patient and goes away with the phenotype.
    # CASCADE throughout: a flag about a row a curator deleted has nothing
    # left to say.
    family_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('families.id', ondelete='CASCADE'), nullable=True
    )
    patient_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('patients.id', ondelete='CASCADE'), nullable=True
    )
    variant_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('variants.id', ondelete='CASCADE'), nullable=True
    )
    phenotype_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('phenotypes.id', ondelete='CASCADE'), nullable=True
    )
    occurrence_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('patient_variant_occurrences.id', ondelete='CASCADE'),
        nullable=True,
    )
    # The other half when the flag is about a compound-het pair, so it shows
    # on both rows; ``occurrence_id`` is then the first-named half.
    paired_occurrence_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('patient_variant_occurrences.id', ondelete='CASCADE'),
        nullable=True,
    )
    # TaskType name of the agent that raised it. A re-run of that agent
    # replaces its own flags (within its own scope -- the patient, for a
    # per-patient task) and leaves every other agent's alone.
    source: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)

    resolved_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Write-once (see FlagResolveRequest): the API refuses a second resolve.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    paper: Mapped['PaperDB'] = relationship('PaperDB', back_populates='flags')
    family: Mapped['FamilyDB | None'] = relationship('FamilyDB')
    patient: Mapped['PatientDB | None'] = relationship('PatientDB')
    variant: Mapped['VariantDB | None'] = relationship('VariantDB')
    phenotype: Mapped['PhenotypeDB | None'] = relationship('PhenotypeDB')
    occurrence: Mapped['PatientVariantOccurrenceDB | None'] = relationship(
        'PatientVariantOccurrenceDB', foreign_keys=[occurrence_id]
    )
    paired_occurrence: Mapped['PatientVariantOccurrenceDB | None'] = relationship(
        'PatientVariantOccurrenceDB', foreign_keys=[paired_occurrence_id]
    )
    resolved_by: Mapped['UserDB | None'] = relationship('UserDB')

    __table_args__ = (
        Index('ix_flags_paper_id', 'paper_id'),
        Index('ix_flags_patient_id', 'patient_id'),
        Index('ix_flags_variant_id', 'variant_id'),
    )


class FlagResp(BaseModel):
    id: int
    paper_id: int
    source: str
    subject: str
    # Lenient on load (no required source), same as every other *_evidence
    # field served to the UI.
    evidence: HumanEvidenceBlock[str]
    # Which rows it is about; null when the flag is not about one. The UI
    # already holds the paper's rows and looks the label up by id.
    family_id: int | None = None
    patient_id: int | None = None
    variant_id: int | None = None
    phenotype_id: int | None = None
    occurrence_id: int | None = None
    paired_occurrence_id: int | None = None
    resolved_by_user_id: int | None = None
    resolved_by: UserSummaryResp | None = None
    resolved_at: UtcDatetime | None = None
    resolution_note: str | None = None
    created_at: UtcDatetime


class FlagResolveRequest(BaseModel):
    """Resolving is one-way and write-once: who looked, when, and what they
    decided. There is no reopen -- a resolution that turns out wrong is
    answered by editing or deleting the row the flag points at, which is
    logged in its own right -- so the row needs no history of its own."""

    note: str | None = None


class FlagBulkResolveRequest(BaseModel):
    """Resolve several flags at once with one note -- the Flags tab's
    "Resolve all" on whatever its filters show, typically every open flag
    from one agent. The ids are explicit rather than a filter re-run on the
    server, so what gets resolved is exactly what the curator was looking
    at. Flags already resolved are left as they are (their first resolution
    stands, as for the single endpoint), not refused, since a list that
    went stale between loading and clicking is the normal case."""

    flag_ids: list[int] = Field(min_length=1)
    note: str | None = None


class FlagRerunRequest(BaseModel):
    """Re-run the agent that raised a flag, for the row it ran on, with the
    curator's note as the follow-up context. The task is the same one the
    scoped rerun buttons queue (see ``/papers/{id}/flags/{flag_id}/rerun``):
    the agent's session still holds its previous run, so the note reads as a
    reply to the flag. Its re-run replaces the flag along with the rest of
    that agent's flags for the scope."""

    note: str | None = None
    skip_successors: bool = False
