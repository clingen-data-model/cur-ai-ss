"""fix_review_status_enum_value_mismatch

Revision ID: 4a424fffb965
Revises: f3a8c2d914b7
Create Date: 2026-09-17 16:55:32.545273

f3a8c2d914b7 backfilled the new `review_status` NOT NULL column with the
lowercase enum *value* ('not_assigned') via a raw SQL server_default. Every
other enum column in this codebase round-trips through the member's *name*
(SQLEnum(SomeEnum) with no values_callable -- see TaskStatus, whose rows
store 'COMPLETED', not 'Completed'), so the ORM failed to map the lowercase
string back to a ReviewStatus member on every read -- a LookupError that
broke GET /papers (and therefore the whole dashboard) for every paper.

This repairs the already-written data and fixes the column's own DEFAULT
clause to match, so a future ALTER-added row gets the correct value even
outside the ORM.

INCIDENT (2026-09-17): the first version of this migration used
`connection.execute(text('PRAGMA foreign_keys = OFF'))`, copied from
f3a8c2d914b7's own (also-buggy) use of that pattern. PRAGMA foreign_keys is
a documented no-op while a transaction is open, and alembic's env.py
(`context.begin_transaction()`) already has one open by the time upgrade()
runs -- so on both migrations the PRAGMA silently did nothing, and batch
mode's drop-and-recreate of `papers` (required here because SQLite has no
ALTER COLUMN for changing a DEFAULT) cascaded, deleting every row in
patients, families, variants, tasks and chat_messages in production.
Recovered from a same-day backup; ~9 hours of work between the backup and
the incident was lost.

The fix, verified against a local reproduction of the exact failure:
`connection.commit()` (closing whichever transaction is already open)
*before* the PRAGMA, using `exec_driver_sql` rather than `execute(text(...))`
for the PRAGMA itself. Every other migration using the old
execute(text('PRAGMA foreign_keys = OFF')) pattern (grep the repo for it)
carries the same latent bug -- they happened not to trigger it, either
because their batch operation didn't require a full table recreation or
their target table has no CASCADE children. Use this migration's pattern,
not CLAUDE.md's older documented one, for any future batch_alter_table on a
table with CASCADE dependents.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4a424fffb965'
down_revision: Union[str, None] = 'f3a8c2d914b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# lowercase value -> uppercase name, for every ReviewStatus member.
_VALUE_TO_NAME = {
    'not_assigned': 'NOT_ASSIGNED',
    'assigned': 'ASSIGNED',
    'in_progress': 'IN_PROGRESS',
    'completed': 'COMPLETED',
}


def upgrade() -> None:
    connection = op.get_bind()
    for value, name in _VALUE_TO_NAME.items():
        connection.execute(
            sa.text(
                'UPDATE papers SET review_status = :name WHERE review_status = :value'
            ),
            {'name': name, 'value': value},
        )

    connection.commit()
    connection.exec_driver_sql('PRAGMA foreign_keys = OFF')
    try:
        with op.batch_alter_table('papers', schema=None) as batch_op:
            batch_op.alter_column(
                'review_status',
                existing_type=sa.Enum(
                    'not_assigned',
                    'assigned',
                    'in_progress',
                    'completed',
                    name='reviewstatus',
                ),
                server_default='NOT_ASSIGNED',
            )
    finally:
        connection.exec_driver_sql('PRAGMA foreign_keys = ON')
        connection.commit()


def downgrade() -> None:
    connection = op.get_bind()
    connection.commit()
    connection.exec_driver_sql('PRAGMA foreign_keys = OFF')
    try:
        with op.batch_alter_table('papers', schema=None) as batch_op:
            batch_op.alter_column(
                'review_status',
                existing_type=sa.Enum(
                    'not_assigned',
                    'assigned',
                    'in_progress',
                    'completed',
                    name='reviewstatus',
                ),
                server_default='not_assigned',
            )
    finally:
        connection.exec_driver_sql('PRAGMA foreign_keys = ON')
        connection.commit()

    for value, name in _VALUE_TO_NAME.items():
        connection.execute(
            sa.text(
                'UPDATE papers SET review_status = :value WHERE review_status = :name'
            ),
            {'name': name, 'value': value},
        )
