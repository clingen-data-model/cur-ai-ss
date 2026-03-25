"""remove gene from variants

Revision ID: 8e4d825938c2
Revises: eb6bb798b30f
Create Date: 2026-03-25 16:56:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8e4d825938c2'
down_revision: Union[str, None] = 'eb6bb798b30f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('variants', schema=None) as batch_op:
        batch_op.drop_column('gene')


def downgrade() -> None:
    with op.batch_alter_table('variants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('gene', sa.String(), nullable=False))
