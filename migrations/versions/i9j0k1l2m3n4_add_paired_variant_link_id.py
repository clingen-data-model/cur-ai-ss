"""add paired_variant_link_id for diplotype grouping

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-05-21 22:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'i9j0k1l2m3n4'
down_revision: Union[str, None] = 'h8i9j0k1l2m3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('patient_variant_links', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('paired_variant_link_id', sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            'fk_patient_variant_links_paired',
            'patient_variant_links',
            ['paired_variant_link_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_index(
            'ix_patient_variant_links_paired_variant_link_id',
            ['paired_variant_link_id'],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('patient_variant_links', schema=None) as batch_op:
        batch_op.drop_index('ix_patient_variant_links_paired_variant_link_id')
        batch_op.drop_constraint('fk_patient_variant_links_paired', type_='foreignkey')
        batch_op.drop_column('paired_variant_link_id')
