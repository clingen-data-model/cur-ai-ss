"""add patient_variant_occurrences.updated_by_user_id

Every other entity table (papers, patients, variants, families,
phenotypes, segregation evidence) already carries a row-level
updated_by_user_id column; occurrences were the one gap, which forced
per-field attribution into the evidence JSON blobs instead (see
lib/models/evidence_block.py's removed edited_by_user_id/edited_by_name/
edited_at -- this migration is the schema half of retiring those).

No PRAGMA foreign_keys dance needed here: nothing CASCADEs onto
patient_variant_occurrences (its only self-referencing FK,
paired_variant_link_id, is ON DELETE SET NULL), so batch_alter_table's
SQLite table-recreate can't trigger an unwanted cascade.

Revision ID: c1deded836a4
Revises: d4f7a2b8c1e9
Create Date: 2026-09-18
"""

import sqlalchemy as sa
from alembic import op

revision = 'c1deded836a4'
down_revision = 'd4f7a2b8c1e9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('patient_variant_occurrences', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('updated_by_user_id', sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            'fk_patient_variant_occurrences_updated_by_user_id',
            'users',
            ['updated_by_user_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_index(
            'ix_patient_variant_occurrences_updated_by_user_id',
            ['updated_by_user_id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('patient_variant_occurrences', schema=None) as batch_op:
        batch_op.drop_index('ix_patient_variant_occurrences_updated_by_user_id')
        batch_op.drop_constraint(
            'fk_patient_variant_occurrences_updated_by_user_id', type_='foreignkey'
        )
        batch_op.drop_column('updated_by_user_id')
