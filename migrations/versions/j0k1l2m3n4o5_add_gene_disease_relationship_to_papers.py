"""add gene disease relationship fields to papers

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-05-22 08:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'j0k1l2m3n4o5'
down_revision: Union[str, None] = 'i9j0k1l2m3n4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('disease_name', sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column('disease_name_evidence', sa.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('disease_inheritance_mode', sa.String(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('disease_inheritance_mode_evidence', sa.JSON(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.drop_column('disease_inheritance_mode_evidence')
        batch_op.drop_column('disease_inheritance_mode')
        batch_op.drop_column('disease_name_evidence')
        batch_op.drop_column('disease_name')
