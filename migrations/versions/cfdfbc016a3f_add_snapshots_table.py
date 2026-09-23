"""add snapshots table

Revision ID: cfdfbc016a3f
Revises: 8f2c4a1d6e93
Create Date: 2026-09-23 17:50:32.310660

Indexes the metadata that list_snapshots() previously had to read by fully
json.loads()-ing every on-disk snapshot file (including its large `tables`
blob) just to get at the small `meta` block. The on-disk files remain the
source of truth for restoring -- this table is purely a fast, queryable index
over their meta blocks, kept in sync because write_snapshot() now inserts a
row in the same DB transaction as the file write it follows (see
lib/misc/snapshots.py). This is a brand-new table, not an alter of an
existing one, so the batch_alter_table/CASCADE hazard in CLAUDE.md does not
apply here.

Pre-existing on-disk snapshots have no row here until
lib/bin/backfill_snapshot_index.py is run against them.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'cfdfbc016a3f'
down_revision: Union[str, None] = '8f2c4a1d6e93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'snapshots',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('alembic_revision', sa.String(), nullable=True),
        sa.Column('model', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('git_hash', sa.String(), nullable=True),
        sa.Column('state_hash', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('name'),
    )
    op.create_index(
        'ix_snapshots_paper_id_created_at',
        'snapshots',
        ['paper_id', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_snapshots_paper_id_created_at', table_name='snapshots')
    op.drop_table('snapshots')
