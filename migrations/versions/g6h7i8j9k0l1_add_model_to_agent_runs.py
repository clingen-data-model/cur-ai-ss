"""Add model column to agent_runs table

Revision ID: g6h7i8j9k0l1
Revises: f4g5h6i7j8k9
Create Date: 2026-05-21 16:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'g6h7i8j9k0l1'
down_revision: Union[str, None] = 'f4g5h6i7j8k9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'agent_runs',
        sa.Column(
            'model',
            sa.String(255),
            nullable=False,
            server_default='gpt-5-mini',
        ),
    )


def downgrade() -> None:
    op.drop_column('agent_runs', 'model')
