"""rename journal to journal_name and pub_year to publication_year

Revision ID: 6b38768ae59f
Revises: 4d8d51219fe1
Create Date: 2026-03-04 15:33:16.845496

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b38768ae59f'
down_revision: Union[str, None] = '4d8d51219fe1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.alter_column('journal', new_column_name='journal_name')
        batch_op.alter_column('pub_year', new_column_name='publication_year')


def downgrade() -> None:
    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.alter_column('journal_name', new_column_name='journal')
        batch_op.alter_column('publication_year', new_column_name='pub_year')
