"""Remove bad string defaults from agent_run_id columns

Revision ID: h8i9j0k1l2m3
Revises: g6h7i8j9k0l1
Create Date: 2026-05-21 20:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'h8i9j0k1l2m3'
down_revision: Union[str, None] = 'g6h7i8j9k0l1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove DEFAULT '1' from agent_run_id columns."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    for table_name in ['patients', 'variants', 'tasks']:
        if table_name in inspector.get_table_names():
            columns = {col['name'] for col in inspector.get_columns(table_name)}
            if 'agent_run_id' in columns:
                with op.batch_alter_table(table_name) as batch_op:
                    batch_op.alter_column(
                        'agent_run_id',
                        existing_type=sa.Integer(),
                        server_default=None,
                    )


def downgrade() -> None:
    """No downgrade needed."""
    pass
