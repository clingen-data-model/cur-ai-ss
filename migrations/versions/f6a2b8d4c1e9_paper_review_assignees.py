"""A paper's review can be assigned to several curators

`paper_review_assignees` (paper_id, user_id) replaces the single
`papers.review_assignee_user_id`: the review status stays one per paper,
shared by everyone assigned. Every paper that had an assignee gets that one
row.

A new table and an INSERT ... SELECT, so no table is rebuilt and none of the
batch-operation foreign-key pragma dance applies. For the same reason
`papers.review_assignee_user_id` is left where it is, values and all:
dropping a foreign-key column is a rebuild of `papers`, the table every other
one cascades from, and an unread column costs nothing. The model still maps
it and nothing reads or writes it.

Revision ID: f6a2b8d4c1e9
Revises: e5f1a7c3d9b8
Create Date: 2026-11-10 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f6a2b8d4c1e9'
down_revision: Union[str, None] = 'e5f1a7c3d9b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'paper_review_assignees'


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('paper_id', 'user_id'),
    )
    # The join drops an assignee id that no longer names a user, which the
    # new table's foreign key would refuse.
    op.execute(
        f'INSERT INTO {TABLE} (paper_id, user_id) '
        'SELECT papers.id, users.id FROM papers '
        'JOIN users ON users.id = papers.review_assignee_user_id'
    )


def downgrade() -> None:
    # One assignee is all the old column holds: the lowest user id of each
    # paper's set, and NULL for a paper with none.
    op.execute(
        'UPDATE papers SET review_assignee_user_id = ('
        f'SELECT MIN(user_id) FROM {TABLE} WHERE {TABLE}.paper_id = papers.id)'
    )
    op.drop_table(TABLE)
