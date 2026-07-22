"""add patient_variant_occurrences testing_methods_note

Revision ID: fc41fce7ba4b
Revises: e5f6a7b8c9d0
Create Date: 2026-07-22 13:49:52.535226

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'fc41fce7ba4b'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('patient_variant_occurrences', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('testing_methods_note', sa.String(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table('patient_variant_occurrences', schema=None) as batch_op:
        batch_op.drop_column('testing_methods_note')
