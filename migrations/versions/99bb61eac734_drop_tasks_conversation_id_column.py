"""drop tasks conversation_id column

Revision ID: 99bb61eac734
Revises: 4993494a8281
Create Date: 2026-09-14 19:44:41.172048

Removes tasks.conversation_id, the OpenAI Responses API server-side
conversation id that ensure_conversation_id used to mint and the "Rerun Agent
with additional context" handlers used to read and write. It has been
replaced by lib.tasks.agent_session.agent_session: a local SQLiteSession keyed
by the task's own id, stored in {CAA_ROOT}/sqllite/agent_sessions.db rather
than on the task row, and provider-agnostic (the prior conversation_id
mechanism only worked for openai/ models -- LitellmModel ignores it).

tasks has no CASCADE foreign keys pointing to it, so this batch_alter_table
does not need the PRAGMA foreign_keys OFF/ON dance CLAUDE.md requires for
tables with CASCADE dependents.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '99bb61eac734'
down_revision: Union[str, None] = '4993494a8281'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_column('conversation_id')


def downgrade() -> None:
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('conversation_id', sa.String(), nullable=True))
