"""Add conversation_id to tasks table.

Revision ID: a1b2c3d4e5f6
Revises: 2572a7910764
Create Date: 2026-04-16 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '2572a7910764'
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('conversation_id', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_column('conversation_id')
