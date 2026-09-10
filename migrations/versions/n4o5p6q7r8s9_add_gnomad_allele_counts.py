"""add gnomAD allele counts to annotated_variants

Revision ID: n4o5p6q7r8s9
Revises: fc41fce7ba4b
Create Date: 2026-08-26 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'n4o5p6q7r8s9'
down_revision: Union[str, None] = 'fc41fce7ba4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

COLUMNS = (
    'gnomad_ac',
    'gnomad_an',
    'gnomad_popmax_ac',
    'gnomad_popmax_an',
)


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text('PRAGMA foreign_keys = OFF'))

    try:
        with op.batch_alter_table('annotated_variants', schema=None) as batch_op:
            for column in COLUMNS:
                batch_op.add_column(sa.Column(column, sa.Integer(), nullable=True))
    finally:
        connection.execute(sa.text('PRAGMA foreign_keys = ON'))


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text('PRAGMA foreign_keys = OFF'))

    try:
        with op.batch_alter_table('annotated_variants', schema=None) as batch_op:
            for column in COLUMNS:
                batch_op.drop_column(column)
    finally:
        connection.execute(sa.text('PRAGMA foreign_keys = ON'))
