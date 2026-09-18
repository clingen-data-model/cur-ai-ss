"""add_paper_review_status

Revision ID: f3a8c2d914b7
Revises: da29165eddd6
Create Date: 2026-09-17 15:40:00.000000

Adds a review workflow to papers, distinct from the extraction pipeline's
PaperTaskStatus: `review_status` (not_assigned / assigned / in_progress /
completed) plus `review_assignee_user_id`, so a paper can be handed to someone
for curation review.

The FK uses ON DELETE SET NULL, matching updated_by_user_id, so removing a
user unassigns their papers rather than deleting them. papers has CASCADE
dependents (patients, families, variants, tasks, chat_messages all cascade
from papers.id), so PRAGMA foreign_keys is disabled around the batch alter --
see CLAUDE.md and a1b2c3d4e5f6.

`server_default='NOT_ASSIGNED'` is the enum member's *name*, not its value
('not_assigned') -- SQLEnum(ReviewStatus) has no values_callable, so it
round-trips through the name like every other enum column in this codebase
(see TaskStatus). The value was used here originally, which the ORM could
not read back (LookupError on every GET /papers) -- see 4a424fffb965.

PRAGMA foreign_keys is also a no-op while a transaction is open, and
alembic's env.py already has one open by the time upgrade() runs here --
connection.execute(text('PRAGMA foreign_keys = OFF')) alone silently does
nothing, confirmed both by this migration wiping every one of papers'
CASCADE children in production and by a local reproduction. This runs the
PRAGMA inside op.get_context().autocommit_block() -- alembic's own
supported mechanism for stepping outside its managed transaction -- rather
than calling connection.commit() directly, which fixes the PRAGMA but
silently breaks alembic's own post-migration alembic_version bookkeeping
for whichever migration runs last in a given upgrade invocation (its
outer Transaction object ends up deactivated, so its final commit is a
no-op). See 4a424fffb965's docstring for the full incident writeup.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f3a8c2d914b7'
down_revision: Union[str, None] = 'da29165eddd6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    with op.get_context().autocommit_block():
        connection.exec_driver_sql('PRAGMA foreign_keys = OFF')
    try:
        with op.batch_alter_table('papers', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    'review_status',
                    sa.Enum(
                        'not_assigned',
                        'assigned',
                        'in_progress',
                        'completed',
                        name='reviewstatus',
                    ),
                    nullable=False,
                    server_default='NOT_ASSIGNED',
                )
            )
            batch_op.add_column(
                sa.Column('review_assignee_user_id', sa.Integer(), nullable=True)
            )
            batch_op.create_foreign_key(
                'fk_papers_review_assignee_user_id',
                'users',
                ['review_assignee_user_id'],
                ['id'],
                ondelete='SET NULL',
            )
            batch_op.create_index(
                'ix_papers_review_assignee_user_id',
                ['review_assignee_user_id'],
            )
    finally:
        with op.get_context().autocommit_block():
            connection.exec_driver_sql('PRAGMA foreign_keys = ON')


def downgrade() -> None:
    connection = op.get_bind()
    with op.get_context().autocommit_block():
        connection.exec_driver_sql('PRAGMA foreign_keys = OFF')
    try:
        with op.batch_alter_table('papers', schema=None) as batch_op:
            batch_op.drop_index('ix_papers_review_assignee_user_id')
            batch_op.drop_constraint(
                'fk_papers_review_assignee_user_id', type_='foreignkey'
            )
            batch_op.drop_column('review_assignee_user_id')
            batch_op.drop_column('review_status')
    finally:
        with op.get_context().autocommit_block():
            connection.exec_driver_sql('PRAGMA foreign_keys = ON')
