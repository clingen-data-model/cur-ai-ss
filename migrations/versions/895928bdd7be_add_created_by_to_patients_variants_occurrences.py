"""add created_at/created_by_user_id to patients, variants, occurrences

Revision ID: 895928bdd7be
Revises: ae683ef42263
Create Date: 2026-09-25 00:00:00.000000

Lets the UI mark a whole row (not just individual fields) as curator-created
from scratch, distinct from `updated_by_user_id` -- that column is set on
manual creation too (see create_patient/create_variant/create_occurrence in
lib/api/app.py), but is indistinguishable from "pipeline-created, later
edited by a curator" once a manual edit lands, so a separate creation-time
column is needed. NULL means "not known to be curator-created" (pipeline
rows never set it, matching how updated_by_user_id already works), including
for pre-existing rows backfilled by this migration.

The FK uses ON DELETE SET NULL, matching updated_by_user_id, so removing a
user cannot delete domain data. `patients` and `variants` have CASCADE
dependents (patient_variant_occurrences, harmonized_variants,
annotated_variants, phenotypes), and SQLite's batch_alter_table drops and
recreates the table being altered, so PRAGMA foreign_keys must actually be
off during that -- and per CLAUDE.md, a plain `connection.execute(text(...))`
is a silent no-op inside alembic's already-open transaction. This uses
`autocommit_block()`, the pattern CLAUDE.md documents as actually safe.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '895928bdd7be'
down_revision: Union[str, None] = 'ae683ef42263'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ('patients', 'variants', 'patient_variant_occurrences')


def upgrade() -> None:
    connection = op.get_bind()
    with op.get_context().autocommit_block():
        connection.exec_driver_sql('PRAGMA foreign_keys = OFF')

    try:
        for table in _TABLES:
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.add_column(
                    sa.Column(
                        'created_at',
                        sa.DateTime(timezone=True),
                        server_default=sa.func.now(),
                        nullable=False,
                    )
                )
                batch_op.add_column(
                    sa.Column('created_by_user_id', sa.Integer(), nullable=True)
                )
                batch_op.create_foreign_key(
                    f'fk_{table}_created_by_user_id',
                    'users',
                    ['created_by_user_id'],
                    ['id'],
                    ondelete='SET NULL',
                )
                batch_op.create_index(
                    f'ix_{table}_created_by_user_id',
                    ['created_by_user_id'],
                )
    finally:
        with op.get_context().autocommit_block():
            connection.exec_driver_sql('PRAGMA foreign_keys = ON')


def downgrade() -> None:
    connection = op.get_bind()
    with op.get_context().autocommit_block():
        connection.exec_driver_sql('PRAGMA foreign_keys = OFF')

    try:
        for table in _TABLES:
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.drop_index(f'ix_{table}_created_by_user_id')
                batch_op.drop_constraint(
                    f'fk_{table}_created_by_user_id', type_='foreignkey'
                )
                batch_op.drop_column('created_by_user_id')
                batch_op.drop_column('created_at')
    finally:
        with op.get_context().autocommit_block():
            connection.exec_driver_sql('PRAGMA foreign_keys = ON')
