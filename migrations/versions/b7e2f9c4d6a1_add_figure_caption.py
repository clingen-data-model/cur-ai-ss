"""Add figure_descriptions.caption: the legend as printed, kept with the row

The caption the Figure Description step reads to the vision model has only
ever lived in the anchored Markdown, as the alt text of the figure's
``[figure-N] ![caption](...)`` line, so the figures page could not show a
figure beside its legend without parsing the document on every request.
The step now stores the caption it read on the row, and the figures endpoint
serves it. Nullable: a figure Docling attached no caption to has none.

Rows from before this migration are filled from the anchored text on disk
by ``lib.bin.backfill_figure_captions`` (no model call: the text is the same
the step would read on a re-run), not here. Migrations run against databases
whose document folder may not exist (CI, tests), so none of them reads it.

A plain ADD COLUMN, which SQLite does in place: no table rewrite, so no
batch operation and no foreign-key pragma dance. Nothing CASCADEs onto
figure_descriptions either way.

Revision ID: b7e2f9c4d6a1
Revises: 7c1e5a9d3b2f
Create Date: 2026-10-27 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7e2f9c4d6a1'
down_revision: Union[str, None] = '7c1e5a9d3b2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'figure_descriptions', sa.Column('caption', sa.Text(), nullable=True)
    )


def downgrade() -> None:
    with op.batch_alter_table('figure_descriptions', schema=None) as batch_op:
        batch_op.drop_column('caption')
