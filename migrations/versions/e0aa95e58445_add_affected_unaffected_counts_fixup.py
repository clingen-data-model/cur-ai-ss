"""Add affected_count and unaffected_count to segregation_analysis_computed

Revision ID: e0aa95e58445
Revises: f9e8d7c6b5a4
Create Date: 2026-05-15 15:51:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e0aa95e58445'
down_revision: Union[str, None] = 'f9e8d7c6b5a4'
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('segregation_analysis_computed', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'affected_count', sa.Integer(), nullable=False, server_default='0'
            )
        )
        batch_op.add_column(
            sa.Column(
                'affected_count_reasoning',
                sa.JSON(),
                nullable=False,
                server_default='{}',
            )
        )
        batch_op.add_column(
            sa.Column(
                'unaffected_count', sa.Integer(), nullable=False, server_default='0'
            )
        )
        batch_op.add_column(
            sa.Column(
                'unaffected_count_reasoning',
                sa.JSON(),
                nullable=False,
                server_default='{}',
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('segregation_analysis_computed', schema=None) as batch_op:
        batch_op.drop_column('unaffected_count_reasoning')
        batch_op.drop_column('unaffected_count')
        batch_op.drop_column('affected_count_reasoning')
        batch_op.drop_column('affected_count')
