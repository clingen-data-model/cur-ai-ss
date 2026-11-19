"""Curator sign-off stamps on phenotypes

The same two columns as the occurrence stamp (lib/models/signoff.py,
migration e5f1a7c3d9b8): reviewed_at and reviewed_by_user_id, written by the
HPO review when a curator accepts a term and its link. Existing rows have
never been reviewed, so both are NULL.

Plain ADD COLUMNs, which SQLite does in place: no table rewrite, so none of
the batch-operation foreign-key pragma dance. The user reference goes in as
raw SQL because alembic's add_column drops the inline REFERENCES clause on
SQLite, and SQLite permits ADD COLUMN with a REFERENCES clause only when the
column's default is NULL, which it is.

Revision ID: f7c2a9e4b1d6
Revises: d5f1b3a7c9e2
Create Date: 2026-11-19 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f7c2a9e4b1d6'
down_revision: Union[str, None] = 'd5f1b3a7c9e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'phenotypes'


def upgrade() -> None:
    op.execute(f'ALTER TABLE {TABLE} ADD COLUMN reviewed_at DATETIME')
    op.execute(
        f'ALTER TABLE {TABLE} ADD COLUMN reviewed_by_user_id INTEGER '
        'REFERENCES users (id)'
    )


def downgrade() -> None:
    # Dropping a column is a table rebuild on SQLite, and hpos, flags and
    # edits reference phenotypes with ON DELETE CASCADE, so foreign keys go
    # off first -- via autocommit_block, since PRAGMA foreign_keys is a no-op
    # inside alembic's open transaction (see CLAUDE.md, Database migrations).
    connection = op.get_bind()
    with op.get_context().autocommit_block():
        connection.exec_driver_sql('PRAGMA foreign_keys = OFF')
    try:
        with op.batch_alter_table(TABLE, schema=None) as batch_op:
            batch_op.drop_column('reviewed_by_user_id')
            batch_op.drop_column('reviewed_at')
    finally:
        with op.get_context().autocommit_block():
            connection.exec_driver_sql('PRAGMA foreign_keys = ON')
