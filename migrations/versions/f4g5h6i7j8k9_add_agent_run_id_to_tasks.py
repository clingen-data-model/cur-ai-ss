"""Add agent_run_id to tasks table

Revision ID: f4g5h6i7j8k9
Revises: e3f4g5h6i7j8
Create Date: 2026-05-21 16:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f4g5h6i7j8k9'
down_revision: Union[str, None] = 'e3f4g5h6i7j8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Get the ID of the baseline run (created during previous migration)
    result = conn.execute(sa.text('SELECT id FROM agent_runs ORDER BY id DESC LIMIT 1'))
    run_id = result.scalar() or 1

    # Add agent_run_id column with default
    op.add_column(
        'tasks',
        sa.Column(
            'agent_run_id', sa.Integer(), nullable=False, server_default=str(run_id)
        ),
    )
    op.create_index('ix_tasks_agent_run_id', 'tasks', ['agent_run_id'])


def downgrade() -> None:
    op.drop_index('ix_tasks_agent_run_id', 'tasks')
    op.drop_column('tasks', 'agent_run_id')
