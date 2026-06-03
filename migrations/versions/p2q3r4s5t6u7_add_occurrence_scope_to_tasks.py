"""add occurrence scope to tasks

Revision ID: p2q3r4s5t6u7
Revises: m1n2o3p4q5r6
Create Date: 2026-06-03 18:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'p2q3r4s5t6u7'
down_revision: Union[str, None] = 'm1n2o3p4q5r6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
