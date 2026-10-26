"""Drop the QUEUED task status: any row still carrying it becomes PENDING

QUEUED was the poller's bookkeeping: a row it had claimed but parked in an
in-process queue until a concurrency slot freed. Since 2026-10-26 the worker
claims a task by starting it (lib.bin.worker.start_attempt), so the status
is never written and the enum member is gone. A row still in it, which can
only be one the old worker left behind, has never started an attempt and is
simply waiting, which is what PENDING means; the sweeps used to release such
rows the same way on every start.

Data only. The column is a VARCHAR holding the member's *name* (see CLAUDE.md
on SQLEnum), with no CHECK constraint, so nothing in the schema names the
members and no table rewrite is needed. dev-caa had no QUEUED row on
2026-10-26. Not reversible in the sense of restoring QUEUED rows: downgrade
leaves the data as is, and the old worker handles PENDING fine.

Revision ID: 7c1e5a9d3b2f
Revises: d2f8a6c4e1b9
Create Date: 2026-10-26 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7c1e5a9d3b2f'
down_revision: Union[str, None] = 'd2f8a6c4e1b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE tasks SET status = 'PENDING' WHERE status = 'QUEUED'")


def downgrade() -> None:
    pass
