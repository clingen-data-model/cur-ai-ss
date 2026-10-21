"""papers.paper_global_additional_context: paper-wide notes for every agent

"Re-run everything" lets a curator give context to the whole pipeline. A
task's own additional context is a follow-up to that one task's conversation
and never reaches its successors, so the paper-wide note lives on the paper
row and goes into the paper block every paper-reading agent is given.

The upgrade is a plain nullable ADD COLUMN, so it needs no batch_alter_table.
The downgrade does (SQLite drops the column by rebuilding the table), and
papers has CASCADE dependents, so it follows the foreign-keys-off pattern in
CLAUDE.md.

Revision ID: e8c3a5d1f7b2
Revises: d7b2e4c19f05
Create Date: 2026-10-20 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e8c3a5d1f7b2'
down_revision: Union[str, None] = 'd7b2e4c19f05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'papers', sa.Column('paper_global_additional_context', sa.Text(), nullable=True)
    )


def downgrade() -> None:
    connection = op.get_bind()
    with op.get_context().autocommit_block():
        connection.exec_driver_sql('PRAGMA foreign_keys = OFF')

    try:
        with op.batch_alter_table('papers', schema=None) as batch_op:
            batch_op.drop_column('paper_global_additional_context')
    finally:
        with op.get_context().autocommit_block():
            connection.exec_driver_sql('PRAGMA foreign_keys = ON')
