"""add segregation support - papers scoring method, patient segregation fields, and segregation analyses table

Revision ID: a2f3b4c5d6e7
Revises: c3e1ecc3aa06
Create Date: 2026-04-22 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a2f3b4c5d6e7'
down_revision: Union[str, None] = 'c3e1ecc3aa06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add scoring_method columns to papers
    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('scoring_method', sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column('scoring_method_evidence', sa.JSON(), nullable=True)
        )

    # Add segregation fields to patients
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

    # Create segregation_analyses table
    op.create_table(
        'segregation_analyses',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('family_id', sa.Integer(), nullable=False),
        sa.Column('segregation_count', sa.Integer(), nullable=False),
        sa.Column('lod_score', sa.Float(), nullable=False),
        sa.Column('lod_score_type', sa.Enum('Published', 'Estimated', name='lodscoretype'), nullable=False),
        sa.Column('sequencing_methodology', sa.String(), nullable=False),
        sa.Column('points_assigned', sa.Float(), nullable=False),
        sa.Column('meets_minimum_criteria', sa.Boolean(), nullable=False),
        sa.Column('has_unexplainable_non_segregations', sa.Boolean(), nullable=False),
        sa.Column('segregation_count_evidence', sa.JSON(), nullable=False),
        sa.Column('lod_score_evidence', sa.JSON(), nullable=False),
        sa.Column('lod_score_type_evidence', sa.JSON(), nullable=False),
        sa.Column('sequencing_methodology_evidence', sa.JSON(), nullable=False),
        sa.Column('points_assigned_evidence', sa.JSON(), nullable=False),
        sa.Column('meets_minimum_criteria_evidence', sa.JSON(), nullable=False),
        sa.Column(
            'has_unexplainable_non_segregations_evidence', sa.JSON(), nullable=False
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['family_id'], ['families.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('segregation_analyses', schema=None) as batch_op:
        batch_op.create_index(
            'ix_segregation_analyses_family_id', ['family_id'], unique=False
        )


def downgrade() -> None:
    # Drop segregation_analyses table
    with op.batch_alter_table('segregation_analyses', schema=None) as batch_op:
        batch_op.drop_index('ix_segregation_analyses_family_id')

    op.drop_table('segregation_analyses')

    # Remove segregation fields from patients
    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.drop_column('twin_type_evidence')
        batch_op.drop_column('relationship_to_proband_evidence')
        batch_op.drop_column('is_obligate_carrier_evidence')
        batch_op.drop_column('twin_type')
        batch_op.drop_column('relationship_to_proband')
        batch_op.drop_column('is_obligate_carrier')

    # Remove scoring_method columns from papers
    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.drop_column('scoring_method')
        batch_op.drop_column('scoring_method_evidence')
