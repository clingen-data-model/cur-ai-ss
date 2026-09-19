"""drop_edits_editor_name

edits.editor_name was a frozen snapshot of the curator's display name at edit
time, taken so history stayed readable after a user was renamed or deleted.
In practice this app never hard-deletes a user row (accounts are deactivated
via UserDB.is_active instead -- see lib/api/app.py's register/login flow),
so user_id is expected to always resolve to a real row, and the snapshot's
main justification (surviving a deleted user) doesn't apply. Renamed users
now show their current name on their edit history, matching how row-level
updated_by_user_id/updated_by attribution already works everywhere else in
this app (a live join via the ORM relationship, not a stored snapshot) --
this was previously the one place field-level and row-level attribution
disagreed on that point.

Verified against production before writing this migration: zero edits rows
currently have a NULL user_id, so nothing's attribution becomes unrecoverable
by dropping the column.

No CASCADE hazard here: nothing has a foreign key onto edits.id (it's a leaf
table), so batch_alter_table's SQLite table-recreate can't trigger an
unwanted cascade delete elsewhere -- the PRAGMA foreign_keys dance in
CLAUDE.md is for tables that have CASCADE dependents, which this isn't.

Revision ID: 32bc2c2d591b
Revises: 24aa340de723
Create Date: 2026-09-19 10:03:36.040724

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '32bc2c2d591b'
down_revision: Union[str, None] = '24aa340de723'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('edits', schema=None) as batch_op:
        batch_op.drop_column('editor_name')


def downgrade() -> None:
    """Best-effort: re-adds the column and fills it from each row's *current*
    user name via a live join -- not the name at edit time, since that's
    exactly the information this migration discards. A user_id left NULL
    (should not currently exist -- see the note above) downgrades to
    'Unknown' rather than leaving a NOT NULL column half-populated."""
    with op.batch_alter_table('edits', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('editor_name', sa.String(), nullable=False, server_default='')
        )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            'UPDATE edits SET editor_name = COALESCE('
            "(SELECT TRIM(u.first_name || ' ' || u.last_name) FROM users u "
            'WHERE u.id = edits.user_id), '
            "'Unknown')"
        )
    )

    with op.batch_alter_table('edits', schema=None) as batch_op:
        batch_op.alter_column('editor_name', server_default=None)
