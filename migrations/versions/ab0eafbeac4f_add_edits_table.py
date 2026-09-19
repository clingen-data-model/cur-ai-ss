"""add_edits_table

Append-only per-field edit history, replacing the edited_by_user_id/
edited_by_name/edited_at that used to be duplicated inside every
HumanEvidenceBlock's own evidence JSON (see lib/models/edit.py).

One nullable FK column per trackable entity type ("exclusive arc") instead of
a generic entity_type/entity_id pair: entity_id can never be a real FK when it
points at a different table depending on entity_type, which means no
automatic ON DELETE CASCADE and orphaned edit rows unless every delete
endpoint remembers to clean them up by hand. Each column here is a real FK
with ON DELETE CASCADE, so history is cleaned up for free.

A brand-new table with no existing rows and nothing yet pointing at it, so
none of the CASCADE/PRAGMA-foreign-keys hazards that apply to
batch_alter_table on an existing table (see CLAUDE.md) apply here.

Revision ID: ab0eafbeac4f
Revises: c1deded836a4
Create Date: 2026-09-18 17:55:11.574571

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'ab0eafbeac4f'
down_revision: Union[str, None] = 'c1deded836a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'edits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=True),
        sa.Column('variant_id', sa.Integer(), nullable=True),
        sa.Column('occurrence_id', sa.Integer(), nullable=True),
        sa.Column('family_id', sa.Integer(), nullable=True),
        sa.Column('paper_id', sa.Integer(), nullable=True),
        sa.Column('segregation_evidence_id', sa.Integer(), nullable=True),
        sa.Column('field_name', sa.String(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('editor_name', sa.String(), nullable=False),
        sa.Column(
            'edited_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            '(patient_id IS NOT NULL) + (variant_id IS NOT NULL) + '
            '(occurrence_id IS NOT NULL) + (family_id IS NOT NULL) + '
            '(paper_id IS NOT NULL) + (segregation_evidence_id IS NOT NULL) = 1',
            name='ck_edits_exactly_one_entity',
        ),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['occurrence_id'], ['patient_variant_occurrences.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(['family_id'], ['families.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['segregation_evidence_id'],
            ['segregation_evidence.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_edits_patient_id_field_name', 'edits', ['patient_id', 'field_name']
    )
    op.create_index(
        'ix_edits_variant_id_field_name', 'edits', ['variant_id', 'field_name']
    )
    op.create_index(
        'ix_edits_occurrence_id_field_name', 'edits', ['occurrence_id', 'field_name']
    )
    op.create_index(
        'ix_edits_family_id_field_name', 'edits', ['family_id', 'field_name']
    )
    op.create_index('ix_edits_paper_id_field_name', 'edits', ['paper_id', 'field_name'])
    op.create_index(
        'ix_edits_segregation_evidence_id_field_name',
        'edits',
        ['segregation_evidence_id', 'field_name'],
    )


def downgrade() -> None:
    op.drop_index('ix_edits_segregation_evidence_id_field_name', table_name='edits')
    op.drop_index('ix_edits_paper_id_field_name', table_name='edits')
    op.drop_index('ix_edits_family_id_field_name', table_name='edits')
    op.drop_index('ix_edits_occurrence_id_field_name', table_name='edits')
    op.drop_index('ix_edits_variant_id_field_name', table_name='edits')
    op.drop_index('ix_edits_patient_id_field_name', table_name='edits')
    op.drop_table('edits')
