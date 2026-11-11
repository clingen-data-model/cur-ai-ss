"""Annotated variants keep the ClinVar variation ID

`annotated_variants.clinvar_variation_id` is the ClinVar record the stored
classification was read from, so the UI can link to it. Rows annotated before
this have NULL until Variant Annotation re-runs or
`lib.bin.backfill_clinvar_variation_ids` fills them.

A nullable column added with plain ADD COLUMN, so no table is rebuilt and the
batch-operation foreign-key pragma dance does not apply.

Revision ID: a1c5e9f3b7d2
Revises: f6a2b8d4c1e9
Create Date: 2026-11-11 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1c5e9f3b7d2'
down_revision: Union[str, None] = 'f6a2b8d4c1e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        'annotated_variants',
        sa.Column('clinvar_variation_id', sa.String(), nullable=True),
    )


def downgrade() -> None:
    # SQLite 3.35+ drops a column in place, without a rebuild.
    op.drop_column('annotated_variants', 'clinvar_variation_id')
