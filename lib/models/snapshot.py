from datetime import datetime

from pydantic import BaseModel


class SnapshotMeta(BaseModel):
    """Metadata block of one on-disk extraction snapshot."""

    name: str
    version: int
    created_at: datetime
    paper_id: int
    alembic_revision: str | None = None
    agent_run_id: int | None = None
    model: str | None = None
    git_hash: str | None = None
    state_hash: str


class PaperResetRequest(BaseModel):
    snapshot_name: str
