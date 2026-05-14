"""add affected_count and unaffected_count to segregation_analysis_computed

Revision ID: 3f8g9h0i1j2
Revises: 170ae36b1b74
Create Date: 2026-05-13 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3f8g9h0i1j2'
down_revision: Union[str, None] = '170ae36b1b74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('segregation_analysis_computed', schema=None) as batch_op:
        batch_op.add_column(sa.Column('affected_count', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('affected_count_reasoning', sa.JSON(), nullable=False, server_default='{}'))
        batch_op.add_column(sa.Column('unaffected_count', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('unaffected_count_reasoning', sa.JSON(), nullable=False, server_default='{}'))


def downgrade() -> None:
    with op.batch_alter_table('segregation_analysis_computed', schema=None) as batch_op:
        batch_op.drop_column('unaffected_count_reasoning')
        batch_op.drop_column('unaffected_count')
        batch_op.drop_column('affected_count_reasoning')
        batch_op.drop_column('affected_count')
