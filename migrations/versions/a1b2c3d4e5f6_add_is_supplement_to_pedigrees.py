"""add is_supplement to pedigrees

Revision ID: a1b2c3d4e5f6
Revises: 0ecf9fe1c63b
Create Date: 2026-06-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '0ecf9fe1c63b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('pedigrees', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_supplement', sa.Boolean(), nullable=True))

    conn = op.get_bind()
    conn.execute(
        sa.text('UPDATE pedigrees SET is_supplement = 0 WHERE is_supplement IS NULL')
    )

    with op.batch_alter_table('pedigrees', schema=None) as batch_op:
        batch_op.alter_column('is_supplement', nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('pedigrees', schema=None) as batch_op:
        batch_op.drop_column('is_supplement')
