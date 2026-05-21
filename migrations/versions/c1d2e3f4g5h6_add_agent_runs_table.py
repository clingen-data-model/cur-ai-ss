"""Add agent_runs table for tracking pipeline execution versions

Revision ID: c1d2e3f4g5h6
Revises: f9e8d7c6b5a4
Create Date: 2026-05-21 15:45:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4g5h6'
down_revision: Union[str, None] = 'b8d9e0f1g2h3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agent_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('git_hash', sa.String(40), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
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


def downgrade() -> None:
    op.drop_index('ix_agent_runs_updated_at', 'agent_runs')
    op.drop_index('ix_agent_runs_git_hash', 'agent_runs')
    op.drop_table('agent_runs')
