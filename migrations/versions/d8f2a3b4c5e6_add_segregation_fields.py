"""add segregation fields to papers and patients, create family_segregations table

Revision ID: d8f2a3b4c5e6
Revises: c3e1ecc3aa06
Create Date: 2026-04-21 00:00:00.000000

"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd8f2a3b4c5e6'
down_revision: Union[str, None] = 'c3e1ecc3aa06'
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    # Add columns to papers table
    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('scoring_method', sa.String(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('scoring_method_evidence', sa.JSON(), nullable=True)
        )

    # Add columns to patients table
    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('is_obligate_carrier', sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('is_obligate_carrier_evidence', sa.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('relationship_to_proband', sa.String(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('relationship_to_proband_evidence', sa.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('twin_type', sa.String(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('twin_type_evidence', sa.JSON(), nullable=True)
        )

    # Populate is_obligate_carrier and is_obligate_carrier_evidence with defaults
    connection = op.get_bind()
    connection.execute(
        sa.text(
            'UPDATE patients SET is_obligate_carrier = 0 WHERE is_obligate_carrier IS NULL'
        )
    )
    dummy_evidence = json.dumps(
        {
            'value': False,
            'reasoning': 'Auto-populated during migration',
        }
    )
    connection.execute(
        sa.text(
            'UPDATE patients SET is_obligate_carrier_evidence = :evidence WHERE is_obligate_carrier_evidence IS NULL'
        ),
        {'evidence': dummy_evidence},
    )

    # Make is_obligate_carrier and is_obligate_carrier_evidence NOT NULL
    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.alter_column('is_obligate_carrier', nullable=False)
        batch_op.alter_column('is_obligate_carrier_evidence', nullable=False)

    # Create family_segregations table
    op.create_table(
        'family_segregations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('family_id', sa.Integer(), nullable=False),
        sa.Column('inheritance_mode', sa.String(), nullable=True),
        sa.Column('sequencing_method_class', sa.String(), nullable=True),
        sa.Column('n_affected_segregations', sa.Integer(), nullable=False),
        sa.Column('n_unaffected_segregations', sa.Integer(), nullable=False),
        sa.Column('lod_score_type', sa.String(), nullable=True),
        sa.Column('lod_score', sa.Float(), nullable=True),
        sa.Column('affected_risk', sa.Float(), nullable=False),
        sa.Column('include_in_score', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ['family_id'],
            ['families.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['paper_id'],
            ['papers.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'paper_id',
            'family_id',
            name='uq_family_segregations_paper_family',
        ),
    )
    op.create_index('ix_family_segregations_paper_id', 'family_segregations', ['paper_id'])


def downgrade() -> None:
    op.drop_index('ix_family_segregations_paper_id', table_name='family_segregations')
    op.drop_table('family_segregations')

    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.drop_column('twin_type_evidence')
        batch_op.drop_column('twin_type')
        batch_op.drop_column('relationship_to_proband_evidence')
        batch_op.drop_column('relationship_to_proband')
        batch_op.drop_column('is_obligate_carrier_evidence')
        batch_op.drop_column('is_obligate_carrier')

    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.drop_column('scoring_method_evidence')
        batch_op.drop_column('scoring_method')
