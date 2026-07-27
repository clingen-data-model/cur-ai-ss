"""add mondo linking fields

Revision ID: d4e5f6a7b8c9
Revises: 0ecf9fe1c63b
Create Date: 2026-06-05 15:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = '0ecf9fe1c63b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mondo_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('mondo_term', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('mondo_match_context', sa.JSON(), nullable=True))

    with op.batch_alter_table('patient_variant_occurrences', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mondo_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('mondo_term', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('mondo_match_context', sa.JSON(), nullable=True))

    op.drop_index('ix_tasks_dedup', table_name='tasks')
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('patient_variant_occurrence_id', sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            'fk_tasks_patient_variant_occurrence_id',
            'patient_variant_occurrences',
            ['patient_variant_occurrence_id'],
            ['id'],
            ondelete='CASCADE',
        )
        batch_op.create_index(
            'ix_tasks_patient_variant_occurrence_id',
            ['patient_variant_occurrence_id'],
            unique=False,
        )
    op.create_index(
        'ix_tasks_dedup',
        'tasks',
        [
            'type',
            'paper_id',
            'family_id',
            'patient_id',
            'variant_id',
            'phenotype_id',
            'patient_variant_occurrence_id',
        ],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_tasks_dedup', table_name='tasks')
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_index('ix_tasks_patient_variant_occurrence_id')
        batch_op.drop_constraint(
            'fk_tasks_patient_variant_occurrence_id',
            type_='foreignkey',
        )
        batch_op.drop_column('patient_variant_occurrence_id')
    op.create_index(
        'ix_tasks_dedup',
        'tasks',
        ['type', 'paper_id', 'family_id', 'patient_id', 'variant_id', 'phenotype_id'],
        unique=True,
    )

    with op.batch_alter_table('patient_variant_occurrences', schema=None) as batch_op:
        batch_op.drop_column('mondo_match_context')
        batch_op.drop_column('mondo_term')
        batch_op.drop_column('mondo_id')

    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.drop_column('mondo_match_context')
        batch_op.drop_column('mondo_term')
        batch_op.drop_column('mondo_id')
