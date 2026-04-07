"""add families table and family_id to patients

Revision ID: 3cd5e8f1a2b4
Revises: e1f2g3h4i5j6
Create Date: 2026-04-06 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '3cd5e8f1a2b4'
down_revision: Union[str, None] = 'e1f2g3h4i5j6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'families',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('identifier', sa.String(), nullable=False),
        sa.Column('identifier_evidence', sa.JSON(), nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_families_paper_id', 'families', ['paper_id'], unique=False)

    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.add_column(sa.Column('family_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_patients_family_id',
            'families',
            ['family_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_index('ix_patients_family_id', ['family_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.drop_index('ix_patients_family_id')
        batch_op.drop_constraint('fk_patients_family_id', type_='foreignkey')
        batch_op.drop_column('family_id')

    op.drop_index('ix_families_paper_id', table_name='families')
    op.drop_table('families')
