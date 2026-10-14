"""add flags

Revision ID: c4e1f7a92b63
Revises: b7a96f15119d
Create Date: 2026-10-14 09:00:00.000000

A new table, so no batch_alter_table and nothing for the CASCADE caveat in
CLAUDE.md to bite on. See lib/models/flag.py for what a row is.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4e1f7a92b63'
down_revision: Union[str, None] = 'b7a96f15119d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'flags',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('family_id', sa.Integer(), nullable=True),
        sa.Column('patient_id', sa.Integer(), nullable=True),
        sa.Column('variant_id', sa.Integer(), nullable=True),
        sa.Column('phenotype_id', sa.Integer(), nullable=True),
        sa.Column('occurrence_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('subject', sa.Text(), nullable=False),
        sa.Column('evidence', sa.JSON(), nullable=False),
        sa.Column('resolved_by_user_id', sa.Integer(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolution_note', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['family_id'], ['families.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['phenotype_id'], ['phenotypes.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['occurrence_id'],
            ['patient_variant_occurrences.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['resolved_by_user_id'], ['users.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_flags_paper_id', 'flags', ['paper_id'], unique=False)
    op.create_index('ix_flags_patient_id', 'flags', ['patient_id'], unique=False)
    op.create_index('ix_flags_variant_id', 'flags', ['variant_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_flags_variant_id', table_name='flags')
    op.drop_index('ix_flags_patient_id', table_name='flags')
    op.drop_index('ix_flags_paper_id', table_name='flags')
    op.drop_table('flags')
