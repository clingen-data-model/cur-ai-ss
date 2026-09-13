from datetime import datetime

from pydantic import BaseModel

from lib.models.datetimes import UtcDatetime
from lib.models.paper import PaperResp


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
    # The pipeline run whose completion produced this snapshot. None on
    # snapshots written before runs were recorded, and on any written outside a
    # run -- a manual backfill, say.
    #
    # Ordering alone cannot answer "revert to before that re-run": a paper's
    # snapshots are a flat list, and which of them predates a given run is only
    # inferable from timestamps. This makes it exact.
    run_id: str | None = None
    state_hash: str
    # Set by the API when listing: whether the paper's current state already
    # matches this snapshot (resetting to it would be a no-op).
    matches_current: bool = False


class PaperResetRequest(BaseModel):
    snapshot_name: str


class PaperResetResp(BaseModel):
    changed: bool
    paper: PaperResp
