"""redo the started_at backfill against stored status names

Revision ID: 98bb28800f61
Revises: acd4fb06fa44
Create Date: 2026-09-13 16:26:11.726780

acd4fb06fa44 backfilled nothing. Its raw SQL filtered on
``status IN ('Completed', 'Failed')`` -- the TaskStatus *values* -- but the
column is ``SQLEnum(TaskStatus)``, which stores the enum *names*. On dev that
matched 0 of 8,694 rows, and the migration reported success.

It went unnoticed because the verification seeded a table by inserting the
literal strings the filter looked for, which confirmed the assumption rather
than the behaviour. Nothing that goes through SQLAlchemy is affected -- it
translates names for you -- so ``/stats`` was correct all along and simply had
no data to report.

This redoes the fill with the stored form. The same seed and distribution are
used, so the values are the ones acd4fb06fa44 intended to write.

"""

import random
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '98bb28800f61'
down_revision: Union[str, None] = 'acd4fb06fa44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Unchanged from acd4fb06fa44, including the seed: the point is to write the
# values that migration meant to.
BACKFILL_MEAN_S = 5 * 60
BACKFILL_STDDEV_S = 2 * 60
BACKFILL_MIN_S = 5
BACKFILL_SEED = 20260913

# The names SQLEnum persists, not the values TaskStatus declares. Spelled out
# rather than imported from the enum, because a migration has to keep meaning
# the same thing after the application's enum is edited.
TERMINAL_STATUS_NAMES = ('COMPLETED', 'FAILED')


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            'SELECT id, updated_at FROM tasks '
            'WHERE started_at IS NULL AND status IN :names'
        ).bindparams(sa.bindparam('names', expanding=True)),
        {'names': list(TERMINAL_STATUS_NAMES)},
    ).fetchall()
    if not rows:
        return

    rng = random.Random(BACKFILL_SEED)
    updates = [
        {
            'task_id': task_id,
            'offset_s': -max(
                BACKFILL_MIN_S,
                round(rng.gauss(BACKFILL_MEAN_S, BACKFILL_STDDEV_S)),
            ),
        }
        for task_id, _ in sorted(rows, key=lambda row: row[0])
    ]

    connection.execute(
        sa.text(
            'UPDATE tasks '
            "SET started_at = datetime(updated_at, :offset_s || ' seconds') "
            'WHERE id = :task_id'
        ),
        updates,
    )


def downgrade() -> None:
    # Only the synthetic values: a real started_at recorded by the worker since
    # this ran belongs to a task whose status changed, and is not ours to erase.
    connection = op.get_bind()
    connection.execute(
        sa.text('UPDATE tasks SET started_at = NULL WHERE status IN :names').bindparams(
            sa.bindparam('names', expanding=True)
        ),
        {'names': list(TERMINAL_STATUS_NAMES)},
    )
