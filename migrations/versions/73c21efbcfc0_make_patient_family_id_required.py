"""make patient family_id required with cascade

Revision ID: 73c21efbcfc0
Revises: 3cd5e8f1a2b4
Branch Labels: None
Depends on: None

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '73c21efbcfc0'
down_revision: Union[str, None] = '3cd5e8f1a2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('patients') as batch_op:
        batch_op.alter_column(
            'family_id',
            existing_type=sa.Integer(),
            nullable=False,
            existing_nullable=True,
            existing_server_default=None,
        )
        batch_op.drop_constraint('fk_patients_family_id', type_='foreignkey')
        batch_op.create_foreign_key(
            'fk_patients_family_id',
            'families',
            ['family_id'],
            ['id'],
            ondelete='CASCADE',
        )


def downgrade() -> None:
    with op.batch_alter_table('patients') as batch_op:
        batch_op.drop_constraint('fk_patients_family_id', type_='foreignkey')
        batch_op.create_foreign_key(
            'fk_patients_family_id',
            'families',
            ['family_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.alter_column(
            'family_id',
            existing_type=sa.Integer(),
            nullable=True,
            existing_nullable=False,
        )
