"""Ensure conversation_id and additional_context columns exist on tasks

Revision ID: f9e8d7c6b5a4
Revises: 79d76bfe280f
Create Date: 2026-05-15 21:50:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = 'f9e8d7c6b5a4'
down_revision: Union[str, None] = '79d76bfe280f'
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # Only proceed if tasks table exists
    if 'tasks' not in inspector.get_table_names():
        return

    columns = [col['name'] for col in inspector.get_columns('tasks')]

    with op.batch_alter_table('tasks', schema=None) as batch_op:
        if 'conversation_ids' in columns:
            batch_op.drop_column('conversation_ids')
        if 'conversation_id' not in columns:
            batch_op.add_column(
                sa.Column('conversation_id', sa.String(), nullable=True)
            )
        if 'additional_context' not in columns:
            batch_op.add_column(
                sa.Column('additional_context', sa.String(), nullable=True)
            )


def downgrade() -> None:
    # This is a fixup migration; downgrade is not well-defined
    # since we're fixing inconsistent state. Just pass.
    pass
