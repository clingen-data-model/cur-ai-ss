"""drop the chat feature

Revision ID: 4993494a8281
Revises: dc1281879b42
Create Date: 2026-09-14 16:00:00.000000

Removes the paper-level chat feature (chat_routing_agent, general_paper_qa_agent,
the four /papers/{id}/chat/* endpoints, the Streamlit chat tab) and the
GENERAL_PAPER_QUESTION pseudo-task it created. It was a proof of concept, ahead
of a proper streaming chat rebuild in the React SPA; the OpenAI-conversation
machinery it depended on (ensure_conversation_id, per-task conversation_id
follow-ups) stays, since that still serves the unrelated "Rerun Agent with
additional context" feature.

On dev-caa at the time this was written: 21 conversations rows (85 messages
across them) and zero GENERAL_PAPER_QUESTION task rows. The DELETE below is a
defensive no-op there and a real cleanup on any other environment that has
chat task rows -- SQLEnum stores the Python member NAME, so a leftover
'GENERAL_PAPER_QUESTION' row would fail to deserialize once that name is gone
from lib.tasks.models.TaskType, per CLAUDE.md's migration-safety notes.

This drops real conversation history. That data loss is deliberate and
irreversible -- downgrade() recreates the empty table, not its rows.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4993494a8281'
down_revision: Union[str, None] = 'dc1281879b42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Defensive: see module docstring. Confirmed 0 rows on dev-caa.
    op.execute(sa.text("DELETE FROM tasks WHERE type = 'GENERAL_PAPER_QUESTION'"))

    op.drop_index('ix_conversations_paper_id', table_name='conversations')
    op.drop_table('conversations')


def downgrade() -> None:
    """Recreates the table structure, not the deleted rows or task history --
    schema-only, like every downgrade, but worth saying explicitly here since
    what upgrade() removed was real user data, not just an empty structure."""
    op.create_table(
        'conversations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.String(), nullable=True),
        sa.Column('messages', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('paper_id'),
    )
    op.create_index(
        'ix_conversations_paper_id', 'conversations', ['paper_id'], unique=True
    )
