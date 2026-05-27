"""ensure papers tags column exists

Revision ID: 9b1c2d3e4f5a
Revises: 8105ee8d0c04
Create Date: 2026-05-27 13:50:00.000000

"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9b1c2d3e4f5a'
down_revision: Union[str, None] = '8105ee8d0c04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column['name'] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _column_names('papers')
    if 'tags' in columns:
        return

    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('tags', sa.JSON(), nullable=False, server_default='[]')
        )

    if 'tag' not in columns:
        return

    bind = op.get_bind()
    rows = bind.execute(sa.text('SELECT id, tag FROM papers WHERE tag IS NOT NULL'))
    for paper_id, tag in rows:
        bind.execute(
            sa.text('UPDATE papers SET tags = :tags WHERE id = :paper_id'),
            {'paper_id': paper_id, 'tags': json.dumps([tag])},
        )


def downgrade() -> None:
    if 'tags' not in _column_names('papers'):
        return

    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.drop_column('tags')
