"""Drop papers.paper_global_additional_context: a note on PDF Parsing is the run-all note

The paper-wide curator note ("re-run everything" set it, every agent read it
on every later run) is replaced by the note on a re-run of the root task:
since b7e3d9a1c5f2 a task's additional_context comes down the successor
graph to every descendant of that run, and everything descends from PDF
Parsing and Paper Classifier. One mechanism, and the note lives on that one
re-run instead of lingering on the paper. POST /papers/{id}/rerun-all is
gone with the column; the dialog queues PDF Parsing (or Paper Classifier,
to keep the parse) through POST /papers/{id}/tasks like any other task.

A native ALTER TABLE DROP COLUMN (SQLite 3.35+; dev-caa runs 3.45, the dev
machines 3.53), not a batch rewrite, so the CASCADE caveat in CLAUDE.md does
not apply. The column is unindexed and unconstrained, which is what the
native form requires. Whatever notes rows still carry are dropped with it:
no run reads them any more (two papers on dev-caa carried one on
2026-10-22; curators re-enter such a note on the next re-run).

Revision ID: d2f8a6c4e1b9
Revises: b7e3d9a1c5f2
Create Date: 2026-10-22 20:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd2f8a6c4e1b9'
down_revision: Union[str, None] = 'b7e3d9a1c5f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('papers', 'paper_global_additional_context')


def downgrade() -> None:
    op.add_column(
        'papers',
        sa.Column('paper_global_additional_context', sa.Text(), nullable=True),
    )
