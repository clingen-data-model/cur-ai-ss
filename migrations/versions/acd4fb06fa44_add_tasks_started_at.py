"""add tasks started_at, with a synthetic backfill

Revision ID: acd4fb06fa44
Revises: 5767de58a19b
Create Date: 2026-09-13 13:43:01.548853

"""

import random
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'acd4fb06fa44'
down_revision: Union[str, None] = '5767de58a19b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Synthetic durations, in seconds. Existing rows have no recorded start time --
# the worker only began stamping one as of this revision -- so these are made
# up, to give the progress estimates something to work with before real runs
# accumulate.
BACKFILL_MEAN_S = 5 * 60
BACKFILL_STDDEV_S = 2 * 60

# N(300, 120) puts ~0.62% of draws at or below zero, which on ~9k rows is ~56
# tasks that would appear to start after they finished. Clamped so every
# synthetic duration is positive and plausibly short rather than impossible.
BACKFILL_MIN_S = 5

# Fixed so the backfill is reproducible: rerunning this migration on another
# copy of the same database produces the same values, which makes anything
# derived from them comparable across environments.
BACKFILL_SEED = 20260913


def upgrade() -> None:
    # Plain ADD COLUMN, not batch_alter_table. On SQLite batch mode copies the
    # table, drops the original and renames the copy -- and `tasks` both holds
    # ~9k rows on dev and carries a CASCADE foreign key to papers, which is the
    # shape that emptied the patients table in 3b2d941d02a2. SQLite does ADD
    # COLUMN in place, so the hazard never arises.
    op.add_column(
        'tasks',
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    )

    # --- Synthetic backfill ------------------------------------------------
    #
    # These values are invented. They are not measurements, and anything
    # computed from them -- median task duration, a progress estimate, a "~4 min
    # left" label -- is fiction until real runs outnumber them. That is the
    # point: without a backfill the progress feature shows nothing at all until
    # weeks of real pipeline runs accumulate.
    #
    # Two deliberate narrowings of "fill in existing rows":
    #
    # Only terminal tasks. A PENDING or QUEUED task has genuinely never started,
    # and giving it a start time would make it look like work in flight -- which
    # is exactly what the progress bars read. RUNNING is excluded for the same
    # reason: whatever the worker does next would overwrite it anyway.
    #
    # Only rows that are still NULL, so re-running this cannot overwrite a real
    # measurement recorded after the column shipped.
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            'SELECT id, updated_at FROM tasks '
            "WHERE started_at IS NULL AND status IN ('Completed', 'Failed')"
        )
    ).fetchall()
    if not rows:
        return

    rng = random.Random(BACKFILL_SEED)
    updates = [
        {
            'task_id': task_id,
            # Ordered by id so the seeded sequence maps to the same row every
            # time, independent of whatever order the SELECT happened to return.
            'offset_s': -max(
                BACKFILL_MIN_S,
                round(rng.gauss(BACKFILL_MEAN_S, BACKFILL_STDDEV_S)),
            ),
        }
        for task_id, _ in sorted(rows, key=lambda row: row[0])
    ]

    # Computed by SQLite from each row's own updated_at rather than in Python,
    # so the stored text format matches exactly what the app writes.
    connection.execute(
        sa.text(
            'UPDATE tasks '
            "SET started_at = datetime(updated_at, :offset_s || ' seconds') "
            'WHERE id = :task_id'
        ),
        updates,
    )


def downgrade() -> None:
    op.drop_column('tasks', 'started_at')
