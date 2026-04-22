"""Add segregation fields to patients.

Revision ID: 7f8c9d3e5a2b
Revises: 50d7e319ffa3
Create Date: 2026-04-21 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7f8c9d3e5a2b'
down_revision: Union[str, None] = '50d7e319ffa3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('is_obligate_carrier', sa.Boolean(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('relationship_to_proband', sa.String(), nullable=True)
        )
        batch_op.add_column(sa.Column('twin_type', sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column('is_obligate_carrier_evidence', sa.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('relationship_to_proband_evidence', sa.JSON(), nullable=True)
        )
        batch_op.add_column(sa.Column('twin_type_evidence', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.drop_column('twin_type_evidence')
        batch_op.drop_column('relationship_to_proband_evidence')
        batch_op.drop_column('is_obligate_carrier_evidence')
        batch_op.drop_column('twin_type')
        batch_op.drop_column('relationship_to_proband')
        batch_op.drop_column('is_obligate_carrier')
