"""add vep_consequence to annotated_variants

Revision ID: b7e4a1f92c3d
Revises: 4a424fffb965
Create Date: 2026-09-17 16:10:00.000000

annotated_variants has no CASCADE foreign keys pointing to it, so the
PRAGMA toggle below is not load-bearing the way it was for f3a8c2d914b7 --
kept anyway for consistency with every other batch_alter_table in this
codebase.

Uses `op.get_context().autocommit_block()` around the PRAGMA rather than a
manual `connection.commit()`: the latter is what f3a8c2d914b7 and
4a424fffb965 originally used (per the pattern CLAUDE.md documented after
56513577), and it silently breaks alembic's own version bookkeeping --
committing the connection alembic's MigrationContext is mid-transaction on
causes the post-upgrade() `UPDATE alembic_version` to land in a transaction
nothing ever commits, so alembic_version does not advance even though the
schema change itself lands. Reproduced locally: `alembic upgrade head` then
`alembic upgrade head` again re-attempts an already-applied batch alter and
fails (duplicate column / circular dependency depending on the migration).
autocommit_block() is alembic's own supported mechanism for stepping outside
its managed transaction and back in, and does not have this problem --
verified by the same reproduction plus a CASCADE parent/child survival
check. f3a8c2d914b7 and 4a424fffb965 are fixed the same way in this branch.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7e4a1f92c3d'
down_revision: Union[str, None] = '4a424fffb965'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    connection = op.get_bind()
    with op.get_context().autocommit_block():
        connection.exec_driver_sql('PRAGMA foreign_keys = OFF')

    try:
        with op.batch_alter_table('annotated_variants', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column('vep_consequence', sa.String(), nullable=True)
            )
    finally:
        with op.get_context().autocommit_block():
            connection.exec_driver_sql('PRAGMA foreign_keys = ON')


def downgrade() -> None:
    connection = op.get_bind()
    with op.get_context().autocommit_block():
        connection.exec_driver_sql('PRAGMA foreign_keys = OFF')

    try:
        with op.batch_alter_table('annotated_variants', schema=None) as batch_op:
            batch_op.drop_column('vep_consequence')
    finally:
        with op.get_context().autocommit_block():
            connection.exec_driver_sql('PRAGMA foreign_keys = ON')
