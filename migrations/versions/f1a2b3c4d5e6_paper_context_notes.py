"""paper_context_notes: a paper's additional context as a list of notes

A curator's additional context used to be text: first one per task
(tasks.additional_context, a follow-up into that task's earlier
conversation, which curators picking the wrong task left the right agent
unaware of), then one per paper (papers.paper_global_additional_context,
e8c3a5d1f7b2, which every agent read). One text had no way to show what
each paragraph was for or to take one out once it stopped holding. So the
context becomes a table of notes, each with its source, author, time and
anchor (the step and row it was given for), and both text columns go.

Each paper's text is carried over as one note; a task's text is dropped
with its column: it was only ever read by the next run of that task.

Dropping a column rebuilds the table on SQLite, and papers has CASCADE
dependents, so both drops follow the foreign-keys-off pattern in CLAUDE.md
(tasks has none, but the cost is nil). The new table's own foreign keys are
plain create_table: nothing is rebuilt.

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
    op.create_table(
        'paper_context_notes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('anchor', sa.Text(), nullable=True),
        sa.Column('flag_id', sa.Integer(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['flag_id'], ['flags.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(
            ['created_by_user_id'], ['users.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_paper_context_notes_paper_id', 'paper_context_notes', ['paper_id']
    )

    # Each paper's text becomes one note given to every task, attributed to
    # whoever last touched the paper, since that is who re-ran it with it.
    op.execute(
        sa.text(
            'INSERT INTO paper_context_notes (paper_id, text, source, created_by_user_id) '
            "SELECT id, paper_global_additional_context, 'curator', updated_by_user_id "
            'FROM papers '
            'WHERE paper_global_additional_context IS NOT NULL '
            "AND trim(paper_global_additional_context) != ''"
        )
    )

    connection = op.get_bind()
    with op.get_context().autocommit_block():
        connection.exec_driver_sql('PRAGMA foreign_keys = OFF')

    try:
        with op.batch_alter_table('papers', schema=None) as batch_op:
            batch_op.drop_column('paper_global_additional_context')
        with op.batch_alter_table('tasks', schema=None) as batch_op:
            batch_op.drop_column('additional_context')
    finally:
        with op.get_context().autocommit_block():
            connection.exec_driver_sql('PRAGMA foreign_keys = ON')


def downgrade() -> None:
    op.add_column(
        'papers', sa.Column('paper_global_additional_context', sa.Text(), nullable=True)
    )
    op.add_column('tasks', sa.Column('additional_context', sa.String(), nullable=True))
    # Best effort: the notes back into one text per paper, anchors as
    # bracketed labels, in the order the agents read them.
    op.execute(
        sa.text(
            'UPDATE papers SET paper_global_additional_context = ('
            'SELECT group_concat(CASE WHEN anchor IS NULL THEN text '
            "ELSE '[' || anchor || '] ' || text END, char(10) || char(10)) "
            'FROM (SELECT text, anchor FROM paper_context_notes '
            'WHERE paper_id = papers.id ORDER BY id)) '
            'WHERE id IN (SELECT paper_id FROM paper_context_notes)'
        )
    )
    op.drop_index('ix_paper_context_notes_paper_id', table_name='paper_context_notes')
    op.drop_table('paper_context_notes')
