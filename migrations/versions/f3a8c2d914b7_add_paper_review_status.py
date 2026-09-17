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
    connection.execute(sa.text('PRAGMA foreign_keys = OFF'))
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
                    server_default='not_assigned',
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
        connection.execute(sa.text('PRAGMA foreign_keys = ON'))


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text('PRAGMA foreign_keys = OFF'))
    try:
        with op.batch_alter_table('papers', schema=None) as batch_op:
            batch_op.drop_index('ix_papers_review_assignee_user_id')
            batch_op.drop_constraint(
                'fk_papers_review_assignee_user_id', type_='foreignkey'
            )
            batch_op.drop_column('review_assignee_user_id')
            batch_op.drop_column('review_status')
    finally:
        connection.execute(sa.text('PRAGMA foreign_keys = ON'))
