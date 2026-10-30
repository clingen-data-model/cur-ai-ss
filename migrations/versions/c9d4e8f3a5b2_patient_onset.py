"""Patients get age-at-onset and onset-category columns

Papers give the age a condition began far more often than the age it was
diagnosed, and the demographics agent had no field for it: it wrote onset
into ``age_diagnosis`` for one sib and left the other None from the same
table cell (ADAM22, PMID 35373813; TBC1D8B, PMID 30661770; curator feedback
2026-10). ``age_onset`` and ``age_onset_unit`` follow the other three ages;
``onset_category`` is HPO's onset bucket (Antenatal ... Adult), which holds a
"congenital" that has no integer.

Nullable, no default and no backfill: a row from before this migration reads
back as None until Patient Demographics is re-run for the paper, and a
snapshot from before it still restores (lib.misc.snapshots._coerce_row
accepts a missing nullable column).

Native ALTER TABLE ADD COLUMN / DROP COLUMN, not a batch rewrite: patients has
CASCADE dependents and the CLAUDE.md caveat applies to batch mode.

Revision ID: c9d4e8f3a5b2
Revises: b8c3d7e2f4a1
Create Date: 2026-10-29 22:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c9d4e8f3a5b2'
down_revision: Union[str, None] = 'b8c3d7e2f4a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = [
    sa.Column('age_onset', sa.Integer(), nullable=True),
    sa.Column(
        'age_onset_unit',
        sa.Enum('Years', 'Months', 'Days', name='ageunit'),
        nullable=True,
    ),
    sa.Column('age_onset_evidence', sa.JSON(), nullable=True),
    sa.Column('onset_category', sa.String(), nullable=True),
    sa.Column('onset_category_evidence', sa.JSON(), nullable=True),
]


def upgrade() -> None:
    for column in _COLUMNS:
        op.add_column('patients', column)


def downgrade() -> None:
    for column in reversed(_COLUMNS):
        op.drop_column('patients', column.name)
