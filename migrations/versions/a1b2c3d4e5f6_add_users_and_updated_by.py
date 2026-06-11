"""add users table and updated_by audit columns

Revision ID: a1b2c3d4e5f6
Revises: 0ecf9fe1c63b
Create Date: 2026-06-10 00:00:00.000000

Adds a ``users`` table (email login + bcrypt password + name) and an
``updated_by_user_id`` foreign key on the human-editable domain tables so manual
edits are attributable to a user.

The FK uses ``ON DELETE SET NULL`` (never CASCADE) so removing a user cannot
delete domain data. Every ``batch_alter_table`` is wrapped in
``PRAGMA foreign_keys = OFF/ON`` because these tables have CASCADE dependents and
SQLite drops/recreates the table during a batch alter -- see CLAUDE.md.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '0ecf9fe1c63b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables that gain an updated_by_user_id column referencing users.id.
_AUDITED_TABLES = (
    'papers',
    'patients',
    'families',
    'variants',
    'harmonized_variants',
    'phenotypes',
    'segregation_evidence',
)


def upgrade() -> None:
    # users must exist before any FK references it.
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('first_name', sa.String(), nullable=False),
        sa.Column('last_name', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('is_admin', sa.Boolean(), server_default='0', nullable=False),
        sa.Column(
            'description_of_use_case', sa.String(), nullable=False, server_default=''
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    connection = op.get_bind()
    # Disable FK enforcement: batch alters drop/recreate these tables, and they
    # have CASCADE dependents that would otherwise be wiped during the copy.
    connection.execute(sa.text('PRAGMA foreign_keys = OFF'))
    try:
        for table in _AUDITED_TABLES:
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.add_column(
                    sa.Column('updated_by_user_id', sa.Integer(), nullable=True)
                )
                batch_op.create_foreign_key(
                    f'fk_{table}_updated_by_user_id',
                    'users',
                    ['updated_by_user_id'],
                    ['id'],
                    ondelete='SET NULL',
                )
                batch_op.create_index(
                    f'ix_{table}_updated_by_user_id',
                    ['updated_by_user_id'],
                )
    finally:
        connection.execute(sa.text('PRAGMA foreign_keys = ON'))


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text('PRAGMA foreign_keys = OFF'))
    try:
        for table in _AUDITED_TABLES:
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.drop_index(f'ix_{table}_updated_by_user_id')
                batch_op.drop_constraint(
                    f'fk_{table}_updated_by_user_id', type_='foreignkey'
                )
                batch_op.drop_column('updated_by_user_id')
    finally:
        connection.execute(sa.text('PRAGMA foreign_keys = ON'))

    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')
