"""Add tasks.budget_model: the Rerun dialog's "Quick run" box

A curator can run one task, and everything it triggers, on the cheaper
EXTRACTION_BUDGET_MODEL instead of EXTRACTION_MODEL. The choice is a
property of the run, so it lives on the task row next to skip_successors and
additional_context, comes down the successor graph with them, and is reset
by the next enqueue without it. Existing rows ran on the ordinary model, so
the default is false.

A plain ADD COLUMN with a server default, which SQLite does in place: no
table rewrite, no batch operation, no foreign-key pragma dance. Nothing
CASCADEs onto tasks either way.

Revision ID: c3d9e1f7a2b4
Revises: b7e2f9c4d6a1
Create Date: 2026-10-27 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3d9e1f7a2b4'
down_revision: Union[str, None] = 'b7e2f9c4d6a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'tasks',
        sa.Column('budget_model', sa.Boolean(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_column('budget_model')
