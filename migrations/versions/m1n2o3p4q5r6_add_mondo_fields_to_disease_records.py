"""add mondo fields to disease records

Revision ID: m1n2o3p4q5r6
Revises: 3ba072e85738
Create Date: 2026-05-27 15:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'm1n2o3p4q5r6'
down_revision: Union[str, None] = '3ba072e85738'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mondo_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('mondo_term', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('mondo_match_context', sa.JSON(), nullable=True))

    with op.batch_alter_table('patient_variant_occurrences', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mondo_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('mondo_term', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('mondo_match_context', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('patient_variant_occurrences', schema=None) as batch_op:
        batch_op.drop_column('mondo_match_context')
        batch_op.drop_column('mondo_term')
        batch_op.drop_column('mondo_id')

    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.drop_column('mondo_match_context')
        batch_op.drop_column('mondo_term')
        batch_op.drop_column('mondo_id')
