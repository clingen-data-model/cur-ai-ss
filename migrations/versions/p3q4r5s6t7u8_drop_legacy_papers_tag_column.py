"""drop legacy papers tag column

Revision ID: p3q4r5s6t7u8
Revises: n2o3p4q5r6s7
Create Date: 2026-05-28 17:25:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'p3q4r5s6t7u8'
down_revision: Union[str, None] = 'n2o3p4q5r6s7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column['name'] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if 'tag' not in _column_names('papers'):
        return

    op.drop_column('papers', 'tag')


def downgrade() -> None:
    if 'tag' in _column_names('papers'):
        return

    op.add_column('papers', sa.Column('tag', sa.String(length=13), nullable=True))
