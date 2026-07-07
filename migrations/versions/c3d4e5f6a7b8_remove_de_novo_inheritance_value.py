"""remove De Novo as an Inheritance enum value

De novo is not a mode of inheritance; it's already tracked as its own boolean
column (patient_variant_occurrences.de_novo). This backfills any existing rows
still storing inheritance='De Novo' by setting de_novo=True and resetting
inheritance to 'Unknown', since 'De Novo' is no longer a valid Inheritance value.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-07
"""

import sqlalchemy as sa
from alembic import op

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            'UPDATE patient_variant_occurrences '
            "SET de_novo = 1, inheritance = 'Unknown' "
            "WHERE inheritance = 'De Novo'"
        )
    )


def downgrade() -> None:
    pass
