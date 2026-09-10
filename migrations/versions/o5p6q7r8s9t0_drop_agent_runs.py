"""drop agent_runs table and agent_run_id columns

The agent_runs table stopped tracking anything real: a run row was only ever
created when the table was empty, so every task and domain row pointed at the
initial baseline row forever. Model/git provenance now lives in the extraction
snapshot metadata, sourced from the environment at write time.

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-09-02 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'o5p6q7r8s9t0'
down_revision: Union[str, None] = 'n4o5p6q7r8s9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

_TABLES = ('families', 'patients', 'variants', 'tasks')


def upgrade() -> None:
    connection = op.get_bind()
    # These tables have CASCADE dependents; batch_alter_table recreates them,
    # which would fire CASCADE deletes into child rows with FKs enabled.
    connection.execute(sa.text('PRAGMA foreign_keys = OFF'))
    try:
        for table in _TABLES:
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.drop_index(f'ix_{table}_agent_run_id')
                batch_op.drop_column('agent_run_id')

        op.drop_index('ix_agent_runs_updated_at', table_name='agent_runs')
        op.drop_index('ix_agent_runs_git_hash', table_name='agent_runs')
        op.drop_table('agent_runs')
    finally:
        connection.execute(sa.text('PRAGMA foreign_keys = ON'))


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text('PRAGMA foreign_keys = OFF'))
    try:
        op.create_table(
            'agent_runs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('git_hash', sa.String(40), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column(
                'model', sa.String(255), nullable=False, server_default='gpt-5-mini'
            ),
            sa.Column(
                'updated_at',
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_agent_runs_git_hash', 'agent_runs', ['git_hash'])
        op.create_index('ix_agent_runs_updated_at', 'agent_runs', ['updated_at'])
        connection.execute(
            sa.text(
                'INSERT INTO agent_runs (git_hash, description, updated_at) '
                "VALUES ('baseline', 'Recreated by downgrade', CURRENT_TIMESTAMP)"
            )
        )
        run_id = connection.execute(
            sa.text('SELECT id FROM agent_runs ORDER BY id DESC LIMIT 1')
        ).scalar()

        for table in _TABLES:
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.add_column(
                    sa.Column(
                        'agent_run_id',
                        sa.Integer(),
                        nullable=False,
                        server_default=str(run_id),
                    )
                )
                batch_op.create_foreign_key(
                    f'fk_{table}_agent_run_id',
                    'agent_runs',
                    ['agent_run_id'],
                    ['id'],
                    ondelete='CASCADE',
                )
                batch_op.create_index(f'ix_{table}_agent_run_id', ['agent_run_id'])
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.alter_column('agent_run_id', server_default=None)
    finally:
        connection.execute(sa.text('PRAGMA foreign_keys = ON'))
