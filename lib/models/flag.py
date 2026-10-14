"""Curator flags: a decision an agent made that a curator should look at.

Every extracted value already carries its reasoning, so a flag is not another
copy of that. It exists for the two things a field's reasoning cannot carry:

- a decision about something that was *not* extracted (a candidate the agent
  rejected under a scoping rule, a relative mentioned once without a stated
  fact, a cohort member in another gene), which has no row to hang on; and
- a decision that *was* extracted but turned on a judgment call the paper
  itself leaves open (no proband marked, text and table disagree, a relative
  whose status is only implied).

The row is deliberately thin: who raised it, what it is about, the agent's
evidence block (reasoning plus citations, the same shape as every
``*_evidence`` column so the UI renders it the same way), and who resolved it.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from lib.models.base import Base
from lib.models.datetimes import UtcDatetime
from lib.models.evidence_block import EvidenceBlock, HumanEvidenceBlock
from lib.models.user import UserSummaryResp

if TYPE_CHECKING:
    from lib.models.paper import PaperDB
    from lib.models.patient import PatientDB
    from lib.models.user import UserDB


class ExtractionFlag(BaseModel):
    """One flag as an agent returns it.

    ``patient_identifier`` names the extracted patient the flag is about, or is
    null when the flag is about something that was not extracted -- that is
    the point of a flag, so null is the common case. ``flag.value`` is a short
    subject ("sister of the proband, mentioned as unscreened"); the reasoning
    says what was decided and why; the citations point at the text it rests on.
    """

    patient_identifier: str | None
    flag: EvidenceBlock[str]


class FlagDB(Base):
    __tablename__ = 'flags'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False
    )
    # The extracted row the flag is about, when there is one. CASCADE: a flag
    # about a patient a curator deleted has nothing left to say.
    patient_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('patients.id', ondelete='CASCADE'), nullable=True
    )
    # TaskType name of the agent that raised it. A re-run of that agent
    # replaces its own flags and leaves every other agent's alone.
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    paper: Mapped['PaperDB'] = relationship('PaperDB', back_populates='flags')
    patient: Mapped['PatientDB | None'] = relationship('PatientDB')
    resolved_by: Mapped['UserDB | None'] = relationship('UserDB')

    __table_args__ = (
        Index('ix_flags_paper_id', 'paper_id'),
        Index('ix_flags_patient_id', 'patient_id'),
    )


class FlagResp(BaseModel):
    id: int
    paper_id: int
    patient_id: int | None = None
    patient_identifier: str | None = None
    source: str
    subject: str
    # Lenient on load (no required source), same as every other *_evidence
    # field served to the UI.
    evidence: HumanEvidenceBlock[str]
    resolved_by_user_id: int | None = None
    resolved_by: UserSummaryResp | None = None
    resolved_at: UtcDatetime | None = None
    resolution_note: str | None = None
    created_at: UtcDatetime


class FlagResolveRequest(BaseModel):
    """``resolved`` true marks the flag as looked at by the current user, with
    an optional note; false reopens it and clears the note."""

    resolved: bool
    note: str | None = None
