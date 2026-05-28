"""add mondo match context

Revision ID: n2o3p4q5r6s7
Revises: m1n2o3p4q5r6
Create Date: 2026-05-27 18:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'n2o3p4q5r6s7'
down_revision: Union[str, None] = 'm1n2o3p4q5r6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mondo_match_context', sa.JSON(), nullable=True))

    with op.batch_alter_table('patient_variant_occurrences', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mondo_match_context', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('patient_variant_occurrences', schema=None) as batch_op:
        batch_op.drop_column('mondo_match_context')

    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.drop_column('mondo_match_context')
