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

    # Use batch mode to add agent_run_id column with foreign key
    with op.batch_alter_table('tasks') as batch_op:
        batch_op.add_column(
            sa.Column(
                'agent_run_id', sa.Integer(), nullable=False, server_default=str(run_id)
            )
        )
        batch_op.create_foreign_key(
            'fk_tasks_agent_run_id',
            'agent_runs',
            ['agent_run_id'],
            ['id'],
            ondelete='CASCADE',
        )
        batch_op.create_index('ix_tasks_agent_run_id', ['agent_run_id'])


def downgrade() -> None:
    with op.batch_alter_table('tasks') as batch_op:
        batch_op.drop_index('ix_tasks_agent_run_id')
        batch_op.drop_constraint('fk_tasks_agent_run_id', type_='foreignkey')
        batch_op.drop_column('agent_run_id')
