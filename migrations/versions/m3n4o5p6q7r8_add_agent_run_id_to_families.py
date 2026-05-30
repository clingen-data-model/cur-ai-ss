"""add agent_run_id to families

Revision ID: m3n4o5p6q7r8
Revises: 8105ee8d0c04
Create Date: 2026-05-29 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'm3n4o5p6q7r8'
down_revision: Union[str, None] = '8105ee8d0c04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    conn = op.get_bind()

    result = conn.execute(sa.text('SELECT id FROM agent_runs ORDER BY id DESC LIMIT 1'))
    run_id = result.scalar()
    if not run_id:
        conn.execute(
            sa.text(
                'INSERT INTO agent_runs (git_hash, description, updated_at) '
                "VALUES ('baseline', 'Initial baseline run', CURRENT_TIMESTAMP)"
            )
        )
        result = conn.execute(
            sa.text('SELECT id FROM agent_runs ORDER BY id DESC LIMIT 1')
        )
        run_id = result.scalar()

    with op.batch_alter_table('families', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'agent_run_id',
                sa.Integer(),
                nullable=False,
                server_default=str(run_id),
            )
        )
        batch_op.create_foreign_key(
            'fk_families_agent_run_id',
            'agent_runs',
            ['agent_run_id'],
            ['id'],
            ondelete='CASCADE',
        )
        batch_op.create_index('ix_families_agent_run_id', ['agent_run_id'])

    with op.batch_alter_table('families', schema=None) as batch_op:
        batch_op.alter_column('agent_run_id', server_default=None)


def downgrade() -> None:
    with op.batch_alter_table('families', schema=None) as batch_op:
        batch_op.drop_index('ix_families_agent_run_id')
        batch_op.drop_constraint('fk_families_agent_run_id', type_='foreignkey')
        batch_op.drop_column('agent_run_id')
