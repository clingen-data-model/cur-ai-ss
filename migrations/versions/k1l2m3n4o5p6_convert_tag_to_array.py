"""add tags column for multiple tags

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-05-22 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'k1l2m3n4o5p6'
down_revision: Union[str, None] = 'j0k1l2m3n4o5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the tags column
    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('tags', sa.JSON(), nullable=False, server_default='[]')
        )


def downgrade() -> None:
    # Drop the tags column
    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.drop_column('tags')
