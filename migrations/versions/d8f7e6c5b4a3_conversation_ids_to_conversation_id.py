"""conversation_ids to conversation_id

Revision ID: d8f7e6c5b4a3
Revises: c3e1ecc3aa06
Create Date: 2026-05-15 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd8f7e6c5b4a3'
down_revision: Union[str, None] = 'a2f3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('conversation_id', sa.VARCHAR(), nullable=True))
        batch_op.drop_column('conversation_ids')


def downgrade() -> None:
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'conversation_ids', sa.JSON(), nullable=False, server_default='{}'
            )
        )
        batch_op.drop_column('conversation_id')
