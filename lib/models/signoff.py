"""Curator sign-off: the stamp that says a human checked a row.

A row is either agent-extracted, human-edited (an edits-table row), or
neither; none of those says "a curator looked at this and it is right". The
stamp here does: ``reviewed_at`` and ``reviewed_by_user_id`` on
patient-variant occurrences, written by the review walk one family at a
time (lib/misc/review_cases.py). The occurrence is the unit because it is
what curation is checking -- who carries which variant, how -- and its row
is the patient's and the variant's meeting point; stamping those two as
well (the first design) asked for three confirmations of one fact. The
paper's review progress is the count of stamped occurrences, and the
paper's review status follows it (``sync_review_status``): the first stamp
puts an unassigned paper in progress under the curator who stamped, the
last completes it, and taking a stamp back from a completed paper puts it
in progress again. Open flags do not hold completion back: they are advice
for the curator, who can leave them; the walk's trailing steps for flags
and unlinked variants are optional for the same reason.

A stamp is cleared only by an agent writing the occurrence again in place
(``clear_signoff``, called from compound-het pairing and MONDO linking on an
occurrence): the curator checked values the agent has since replaced.
Occurrence extraction deletes and recreates its rows, so the stamp goes
with the row. A re-run that rewrites the patient or the variant (demographics,
harmonization, annotation) leaves the stamp: the occurrence's own fields
did not change. A curator's own edit never clears a stamp; the editor is a
curator.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterable

from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, Session, declared_attr, mapped_column, relationship

from lib.models.datetimes import UtcDatetime
from lib.models.user import UserSummaryResp

if TYPE_CHECKING:
    from lib.models.paper import PaperDB
    from lib.models.user import UserDB


class SignoffColumns:
    """The two stamp columns, mixed into the occurrence ORM model."""

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # No ON DELETE: SQLite's reflection does not read one off an inline
    # column REFERENCES (which is how the migration adds this column), so the
    # metadata check would never match, and the app never hard-deletes a
    # user anyway (accounts are deactivated, see lib/models/edit.py).
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('users.id'), nullable=True
    )

    @declared_attr
    def reviewed_by(cls) -> Mapped['UserDB | None']:
        return relationship(
            'UserDB',
            foreign_keys=[cls.reviewed_by_user_id],  # type: ignore[list-item]
        )


class SignoffFields(BaseModel):
    """The stamp as the occurrence response carries it."""

    reviewed_at: UtcDatetime | None = None
    reviewed_by: UserSummaryResp | None = None


def signoff_fields(row: SignoffColumns) -> dict[str, Any]:
    """The response fields for ``row``'s stamp, for a ``*Resp`` constructor."""
    return {
        'reviewed_at': row.reviewed_at,
        'reviewed_by': (
            UserSummaryResp.model_validate(row.reviewed_by)
            if row.reviewed_by is not None
            else None
        ),
    }


class SignoffRequest(BaseModel):
    """Body for POST /papers/{paper_id}/signoff: the occurrences to stamp
    (or, with ``confirmed`` false, to unstamp)."""

    occurrence_ids: list[int] = []
    confirmed: bool = True


class SignoffProgress(BaseModel):
    """Stamped occurrences over all of a paper's occurrences."""

    total: int = 0
    confirmed: int = 0


def stamp(row: SignoffColumns, user: UserDB) -> None:
    row.reviewed_at = datetime.now(timezone.utc)
    row.reviewed_by_user_id = user.id
    row.reviewed_by = user


def unstamp(row: SignoffColumns) -> None:
    row.reviewed_at = None
    row.reviewed_by_user_id = None
    row.reviewed_by = None


def clear_signoff(
    session: Session, paper_id: int, rows: Iterable[SignoffColumns | None]
) -> None:
    """An agent rewrote ``rows`` in place: drop their stamps, and if that
    makes a completed paper incomplete, put its review back in progress.
    The assignees are kept; the paper is still theirs to finish."""
    from lib.models.paper import PaperDB, ReviewStatus

    cleared = False
    for row in rows:
        if row is not None and row.reviewed_at is not None:
            unstamp(row)
            cleared = True
    if not cleared:
        return
    paper = session.get(PaperDB, paper_id)
    if paper is not None and paper.review_status == ReviewStatus.COMPLETED:
        paper.review_status = ReviewStatus.IN_PROGRESS


def signoff_progress(session: Session, paper_id: int) -> SignoffProgress:
    from lib.models.patient_variant_occurrences import PatientVariantOccurrenceDB

    table = PatientVariantOccurrenceDB
    total, confirmed = (
        session.query(func.count(table.id), func.count(table.reviewed_at))
        .filter(table.paper_id == paper_id)
        .one()
    )
    return SignoffProgress(total=total, confirmed=confirmed)


def signoff_progress_by_paper(session: Session) -> dict[int, SignoffProgress]:
    """Every paper's progress from one grouped COUNT, for the list endpoint,
    which must not query per paper."""
    from lib.models.patient_variant_occurrences import PatientVariantOccurrenceDB

    table = PatientVariantOccurrenceDB
    rows = (
        session.query(
            table.paper_id, func.count(table.id), func.count(table.reviewed_at)
        )
        .group_by(table.paper_id)
        .all()
    )
    return {
        pid: SignoffProgress(total=total, confirmed=confirmed)
        for pid, total, confirmed in rows
    }


def sync_review_status(session: Session, paper: PaperDB, user: UserDB) -> bool:
    """Bring the paper's review status in line with its stamps, after a
    stamp or a take-back by ``user``. Every occurrence stamped: completed.
    A completed paper with one taken back: in progress again. A stamp on a
    paper nobody has started: in progress. The assignees are kept when there
    are any, else ``user`` becomes the one (in-progress and completed reviews
    always name someone). A paper left in progress with every stamp taken
    back stays in progress: the curator is still on it. Returns whether the
    status changed."""
    from lib.models.paper import ReviewStatus

    progress = signoff_progress(session, paper.id)
    status = paper.review_status
    if progress.total > 0 and progress.confirmed == progress.total:
        wanted = ReviewStatus.COMPLETED
    elif status == ReviewStatus.COMPLETED or (
        progress.confirmed > 0
        and status in (ReviewStatus.NOT_ASSIGNED, ReviewStatus.ASSIGNED)
    ):
        wanted = ReviewStatus.IN_PROGRESS
    else:
        return False
    if wanted == status:
        return False
    paper.review_status = wanted
    if not paper.review_assignees:
        paper.review_assignees.append(user)
    return True
