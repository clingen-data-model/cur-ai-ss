"""Add papers.is_paper_relevant_evidence: the classifier's verdict with its basis

The paper classifier returned a ReasoningBlock[bool] and the handler kept
only the bool and the FailedPaperRelevancy tag, so a paper the pipeline
stopped on showed the tag and nothing else; the one or two sentences saying
which requirement it failed lived in the task's agent conversation alone.
The handler now stores the whole block here and the paper page shows it.

A plain nullable ADD COLUMN, which SQLite does in place: no batch operation,
no foreign-key pragma dance. Rows from before are None and can be filled
from the conversations by lib.bin.backfill_classifier_basis.

Revision ID: d4e8f1a2b3c5
Revises: c3d9e1f7a2b4
Create Date: 2026-10-29 16:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e8f1a2b3c5'
down_revision: Union[str, None] = 'c3d9e1f7a2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'papers',
        sa.Column('is_paper_relevant_evidence', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    # A batch alter recreates papers, and every table that CASCADEs onto it
    # (patients, variants, edits, figure_descriptions, ...) would lose its
    # rows unless foreign keys are off for the rewrite. The PRAGMA is a no-op
    # inside alembic's transaction, hence the autocommit blocks (CLAUDE.md).
    connection = op.get_bind()
    with op.get_context().autocommit_block():
        connection.exec_driver_sql('PRAGMA foreign_keys = OFF')
    try:
        with op.batch_alter_table('papers', schema=None) as batch_op:
            batch_op.drop_column('is_paper_relevant_evidence')
    finally:
        with op.get_context().autocommit_block():
            connection.exec_driver_sql('PRAGMA foreign_keys = ON')
