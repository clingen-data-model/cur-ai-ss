"""rename patient_variant_links to patient_variant_occurrences

Revision ID: 8105ee8d0c04
Revises: 139e89a5eb03
Create Date: 2026-05-25 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = '8105ee8d0c04'
down_revision: Union[str, None] = '139e89a5eb03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('patient_variant_occurrences', schema=None) as batch_op:
        # Drop old indexes
        batch_op.drop_index('ix_patient_variant_links_patient_id')
        batch_op.drop_index('ix_patient_variant_links_variant_id')
        batch_op.drop_index('ix_patient_variant_links_paired_variant_link_id')
        # Drop old constraints
        batch_op.drop_constraint(
            'uq_patient_variant_links_patient_variant', type_='unique'
        )
        batch_op.drop_constraint('fk_patient_variant_links_paired', type_='foreignkey')
        # Create new indexes with correct names
        batch_op.create_index(
            'ix_patient_variant_occurrences_patient_id', ['patient_id'], unique=False
        )
        batch_op.create_index(
            'ix_patient_variant_occurrences_variant_id', ['variant_id'], unique=False
        )
        batch_op.create_index(
            'ix_patient_variant_occurrences_paired_variant_link_id',
            ['paired_variant_link_id'],
            unique=False,
        )
        # Create new constraints with correct names
        batch_op.create_unique_constraint(
            'uq_patient_variant_occurrences_patient_variant',
            ['patient_id', 'variant_id'],
        )
        batch_op.create_foreign_key(
            'fk_patient_variant_occurrences_paired',
            'patient_variant_occurrences',
            ['paired_variant_link_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('patient_variant_occurrences', schema=None) as batch_op:
        batch_op.drop_constraint(
            'uq_patient_variant_occurrences_patient_variant', type_='unique'
        )
        batch_op.drop_index('ix_patient_variant_occurrences_paired_variant_link_id')
        batch_op.drop_index('ix_patient_variant_occurrences_variant_id')
        batch_op.drop_index('ix_patient_variant_occurrences_patient_id')
        batch_op.drop_constraint(
            'fk_patient_variant_occurrences_paired_variant_link_id',
            type_='foreignkey',
        )
        batch_op.create_constraint(
            batch_op.f('uq_patient_variant_links_patient_variant'),
            ['patient_id', 'variant_id'],
            type_='unique',
        )
        batch_op.create_index(
            batch_op.f('ix_patient_variant_links_paired_variant_link_id'),
            ['paired_variant_link_id'],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_patient_variant_links_variant_id'),
            ['variant_id'],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_patient_variant_links_patient_id'),
            ['patient_id'],
            unique=False,
        )
        batch_op.create_foreign_key(
            batch_op.f('fk_patient_variant_links_paired_variant_link_id'),
            'patient_variant_links',
            ['paired_variant_link_id'],
            ['id'],
            ondelete='SET NULL',
        )
    op.rename_table('patient_variant_occurrences', 'patient_variant_links')
