"""drop tasks.additional_context: context is one field on the paper

A task used to carry its own additional context, sent as a follow-up into
that task's earlier conversation. Curators picking the wrong task in the
re-run dialog left the right agent unaware of it, so there is now one
context per paper (papers.paper_global_additional_context, added by
e8c3a5d1f7b2) that every agent reads on every run. Whatever a task row still
holds is dropped with the column: it was only ever read by the next run of
that task, which now reads the paper's context instead.

Nothing references tasks by foreign key, so recreating the table cannot
cascade; the foreign-keys-off pattern from CLAUDE.md is kept all the same,
since the table is recreated and the cost is nil.

Revision ID: f1a2b3c4d5e6
Revises: e8c3a5d1f7b2
Create Date: 2026-10-21 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e8c3a5d1f7b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    with op.get_context().autocommit_block():
        connection.exec_driver_sql('PRAGMA foreign_keys = OFF')

    try:
        with op.batch_alter_table('tasks', schema=None) as batch_op:
            batch_op.drop_column('additional_context')
    finally:
        with op.get_context().autocommit_block():
            connection.exec_driver_sql('PRAGMA foreign_keys = ON')


def downgrade() -> None:
    op.add_column('tasks', sa.Column('additional_context', sa.String(), nullable=True))
