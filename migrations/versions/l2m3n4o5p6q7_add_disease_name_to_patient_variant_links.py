"""add disease_name to patient_variant_links

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-05-22 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'l2m3n4o5p6q7'
down_revision: Union[str, None] = 'k1l2m3n4o5p6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('patient_variant_links', schema=None) as batch_op:
        batch_op.add_column(sa.Column('disease_name', sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column('disease_name_evidence', sa.JSON(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table('patient_variant_links', schema=None) as batch_op:
        batch_op.drop_column('disease_name_evidence')
        batch_op.drop_column('disease_name')
