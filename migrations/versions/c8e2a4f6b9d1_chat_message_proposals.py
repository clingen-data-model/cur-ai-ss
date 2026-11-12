"""Chat messages carry proposed direct edits

An assistant reply in the paper chat can propose direct edits (adding,
removing or relinking phenotypes) that are applied only when the curator
presses Apply: `chat_messages.proposal` holds them, `proposal_status` whether
they were applied or cancelled, and when (who did it is kept in the
proposal JSON, so no foreign key -- and so no table rebuild -- is needed).

Nullable columns added with plain ADD COLUMN, so no table is rebuilt and the
batch-operation foreign-key pragma dance does not apply.

Revision ID: c8e2a4f6b9d1
Revises: a1c5e9f3b7d2
Create Date: 2026-11-11 23:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c8e2a4f6b9d1'
down_revision: Union[str, None] = 'a1c5e9f3b7d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column('chat_messages', sa.Column('proposal', sa.JSON(), nullable=True))
    op.add_column(
        'chat_messages', sa.Column('proposal_status', sa.String(), nullable=True)
    )
    op.add_column(
        'chat_messages',
        sa.Column('proposal_resolved_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    # SQLite 3.35+ drops a column in place, without a rebuild.
    op.drop_column('chat_messages', 'proposal_resolved_at')
    op.drop_column('chat_messages', 'proposal_status')
    op.drop_column('chat_messages', 'proposal')
