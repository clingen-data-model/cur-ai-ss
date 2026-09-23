from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from lib.models.base import Base
from lib.models.datetimes import UtcDatetime
from lib.models.paper import PaperResp


class SnapshotDB(Base):
    """Index row for one on-disk extraction snapshot.

    Mirrors the `meta` block of the snapshot file at
    lib/misc/pdf/paths.py's snapshot_path(paper_id, name) -- the file remains
    the source of truth for restoring, this table exists only so listing
    snapshots is an indexed query instead of a full json.loads() of every
    snapshot file (including its large `tables` blob) on disk. See
    lib/misc/snapshots.py for how the two are kept in sync.
    """

    __tablename__ = 'snapshots'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    alembic_revision: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    git_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    state_hash: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index('ix_snapshots_paper_id_created_at', 'paper_id', 'created_at'),
    )


class SnapshotMeta(BaseModel):
    """Metadata block of one on-disk extraction snapshot."""

    name: str
    version: int
    created_at: UtcDatetime
    paper_id: int
    alembic_revision: str | None = None
    model: str | None = None
    description: str | None = None
    git_hash: str | None = None
    state_hash: str
    # Set by the API when listing: whether the paper's current state already
    # matches this snapshot (resetting to it would be a no-op).
    matches_current: bool = False


class PaperResetRequest(BaseModel):
    snapshot_name: str


class PaperResetResp(BaseModel):
    changed: bool
    paper: PaperResp
