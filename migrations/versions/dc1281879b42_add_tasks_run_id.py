"""add tasks run_id

Revision ID: dc1281879b42
Revises: 98bb28800f61
Create Date: 2026-09-13 17:12:00.000000

Groups a paper's tasks into the run that produced them: one user action, plus
everything enqueue_successors cascades from it.

Existing rows predate the column, so they are assigned inferred ids by splitting
each paper's history on idle gaps. That heuristic is deliberately confined to
this migration. It reads well on the current data -- of 8,600 consecutive-task
gaps, p50 is 5s and p90 is 96s while p99 is 12 days, so runs are separated by
orders of magnitude rather than by a judgement call -- but it is still a guess
about scheduling, and a slow agent or two papers processing at once would break
it. Going forward the id is recorded rather than inferred.

Inferred ids are prefixed so they stay distinguishable from real ones, and a
consumer that wants only trustworthy runs can exclude them.

"""

import uuid
from datetime import datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'dc1281879b42'
down_revision: Union[str, None] = '98bb28800f61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# See the module docstring: chosen from the gap distribution, not by feel.
BURST_IDLE_GAP_S = 30 * 60

# Marks a run this migration guessed at rather than one the app recorded.
INFERRED_PREFIX = 'inferred-'


def _as_datetime(value: object) -> datetime | None:
    """SQLite hands these back as strings on a raw connection, but as datetimes
    under some drivers -- accept either rather than assuming."""
    if value is None or isinstance(value, datetime):
        return value  # type: ignore[return-value]
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('run_id', sa.String(length=36), nullable=True))
    op.create_index('ix_tasks_run_id', 'tasks', ['run_id'])

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            'SELECT id, paper_id, started_at, updated_at FROM tasks '
            'WHERE run_id IS NULL ORDER BY paper_id, COALESCE(started_at, updated_at)'
        )
    ).fetchall()
    if not rows:
        return

    updates: list[dict[str, object]] = []
    current_paper: int | None = None
    current_run: str | None = None
    burst_end: datetime | None = None

    for task_id, paper_id, started_at, updated_at in rows:
        start = _as_datetime(started_at) or _as_datetime(updated_at)
        finish = _as_datetime(updated_at) or start

        # Papers are independent: a new one always begins a new run.
        if paper_id != current_paper:
            current_paper, current_run, burst_end = paper_id, None, None

        idle = (
            None
            if (burst_end is None or start is None)
            else (start - burst_end).total_seconds()
        )
        if current_run is None or idle is None or idle > BURST_IDLE_GAP_S:
            # Short ids: these are groupings, not keys anything joins on.
            current_run = f'{INFERRED_PREFIX}{uuid.uuid4().hex[:16]}'
            burst_end = finish
        elif finish is not None and (burst_end is None or finish > burst_end):
            # Measured against the latest finish rather than the previous start,
            # because tasks overlap -- one beginning while another runs is the
            # same run however long the earlier one has been busy.
            burst_end = finish

        updates.append({'task_id': task_id, 'run_id': current_run})

    connection.execute(
        sa.text('UPDATE tasks SET run_id = :run_id WHERE id = :task_id'), updates
    )


def downgrade() -> None:
    op.drop_index('ix_tasks_run_id', table_name='tasks')
    op.drop_column('tasks', 'run_id')
