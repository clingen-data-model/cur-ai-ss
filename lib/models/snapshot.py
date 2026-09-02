from datetime import datetime

from pydantic import BaseModel

from lib.models.paper import PaperResp


class SnapshotMeta(BaseModel):
    """Metadata block of one on-disk extraction snapshot."""

    name: str
    version: int
    created_at: datetime
    paper_id: int
    alembic_revision: str | None = None
    model: str | None = None
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
