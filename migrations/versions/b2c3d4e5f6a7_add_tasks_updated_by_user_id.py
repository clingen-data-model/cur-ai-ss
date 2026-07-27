"""add tasks.updated_by_user_id

Records which user triggered a task (null = machine-enqueued by the worker).

The batch alter is wrapped in ``PRAGMA foreign_keys = OFF/ON`` per project
convention: SQLite implements ``batch_alter_table`` by recreating the table, and
``tasks`` carries CASCADE foreign keys to papers/families/patients/variants/
phenotypes that must not fire during the copy.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-12
"""

import sqlalchemy as sa
from alembic import op

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text('PRAGMA foreign_keys = OFF'))
    try:
        with op.batch_alter_table('tasks', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column('updated_by_user_id', sa.Integer(), nullable=True)
            )
            batch_op.create_foreign_key(
                'fk_tasks_updated_by_user_id',
                'users',
                ['updated_by_user_id'],
                ['id'],
                ondelete='SET NULL',
            )
            batch_op.create_index(
                'ix_tasks_updated_by_user_id',
                ['updated_by_user_id'],
            )
    finally:
        connection.execute(sa.text('PRAGMA foreign_keys = ON'))


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text('PRAGMA foreign_keys = OFF'))
    try:
        with op.batch_alter_table('tasks', schema=None) as batch_op:
            batch_op.drop_index('ix_tasks_updated_by_user_id')
            batch_op.drop_constraint('fk_tasks_updated_by_user_id', type_='foreignkey')
            batch_op.drop_column('updated_by_user_id')
    finally:
        connection.execute(sa.text('PRAGMA foreign_keys = ON'))
