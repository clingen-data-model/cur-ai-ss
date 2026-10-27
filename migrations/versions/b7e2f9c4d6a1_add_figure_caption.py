"""Add figure_descriptions.caption and caption_source: the legend, kept with the row

The caption the Figure Description step reads to the vision model has only
ever lived in the anchored Markdown, as the alt text of the figure's
``[figure-N] ![caption](...)`` line, so the figures page could not show a
figure beside its legend without parsing the document on every request.
The step now stores the caption it read on the row, with where it came from
(``CaptionSource``: linked by Docling, the block printed beside the picture
by rule, a block the vision model chose, or the model's transcription of a
legend drawn inside the image), and the figures endpoint serves both. Both
nullable, with no default: a figure with no caption has no source either.
The source column is a VARCHAR of the member *name* (see CLAUDE.md on
SQLEnum), with no CHECK constraint.

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
    op.add_column(
        'figure_descriptions',
        sa.Column(
            'caption_source',
            sa.Enum(
                'DOCLING',
                'ADJACENT',
                'MODEL_CHOSEN',
                'MODEL_TRANSCRIBED',
                name='captionsource',
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table('figure_descriptions', schema=None) as batch_op:
        batch_op.drop_column('caption_source')
        batch_op.drop_column('caption')
