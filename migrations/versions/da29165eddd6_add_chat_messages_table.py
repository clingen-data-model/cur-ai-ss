"""add_chat_messages_table

Revision ID: da29165eddd6
Revises: 99bb61eac734
Create Date: 2026-09-17 12:26:18.061935

Rebuilds the chat feature dropped in 4993494a8281, this time one row per
message rather than a single JSON-blob column, so a message-scroller UI can
page and key off individual rows the way it expects a message list to be
shaped.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'da29165eddd6'
down_revision: Union[str, None] = '99bb61eac734'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column(
            'role', sa.Enum('USER', 'ASSISTANT', name='chatrole'), nullable=False
        ),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['created_by_user_id'], ['users.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_chat_messages_paper_id', 'chat_messages', ['paper_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_chat_messages_paper_id', table_name='chat_messages')
    op.drop_table('chat_messages')
