"""add main_focus field to variants

Revision ID: a48bffd58432
Revises: c6f7ab602a6f
Create Date: 2026-04-02 15:33:15.979960
"""

from alembic import op
import sqlalchemy as sa


revision = "a48bffd58432"
down_revision = "c6f7ab602a6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Add columns as nullable, no defaults
    with op.batch_alter_table("variants") as batch_op:
        batch_op.add_column(sa.Column("main_focus", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("main_focus_evidence", sa.JSON(), nullable=True))

    # 2) Backfill existing rows
    op.execute(
        """
        UPDATE variants
        SET
            main_focus = TRUE,
            main_focus_evidence = '{"value": true, "reasoning": "set by migration", "quote": "set by migration"}'
        """
    )

    # 3) Make columns NOT NULL after data is correct
    with op.batch_alter_table("variants") as batch_op:
        batch_op.alter_column("main_focus", nullable=False)
        batch_op.alter_column("main_focus_evidence", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("variants") as batch_op:
        batch_op.drop_column("main_focus_evidence")
        batch_op.drop_column("main_focus")