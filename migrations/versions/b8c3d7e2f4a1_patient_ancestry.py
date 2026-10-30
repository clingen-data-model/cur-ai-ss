"""Patients get an ancestry column

A paper's "Brazilian family of Italian descent" had two places to go,
``country_of_origin`` (an enum of countries) and ``race`` (the census
buckets), and neither holds "Italian": the demographics agent put Italy in
the country for some members of the family and Brazil for others (MODY2
paper, PMID 23085272, curator feedback 2026-10). ``ancestry`` keeps the
descent in the paper's words, so the country is only where the paper places
the family and race only the bucket the descent maps to.

Nullable, no default and no backfill: a row from before this migration reads
back as None (``PatientResp.ancestry``) until Patient Demographics is re-run
for the paper, and a snapshot from before it still restores
(lib.misc.snapshots._coerce_row accepts a missing nullable column).

Native ALTER TABLE ADD COLUMN / DROP COLUMN, not a batch rewrite: patients has
CASCADE dependents and the CLAUDE.md caveat applies to batch mode.

Revision ID: b8c3d7e2f4a1
Revises: a4e7c2d9f1b3
Create Date: 2026-10-29 21:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8c3d7e2f4a1'
down_revision: Union[str, None] = 'a4e7c2d9f1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('patients', sa.Column('ancestry', sa.String(), nullable=True))
    op.add_column('patients', sa.Column('ancestry_evidence', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('patients', 'ancestry_evidence')
    op.drop_column('patients', 'ancestry')
