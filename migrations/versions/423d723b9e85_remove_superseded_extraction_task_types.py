"""remove superseded extraction task types

Single-pass PAPER_EXTRACTION replaced nine reading tasks. Their rows must go
before the enum shrinks: SQLEnum stores member names, so a row naming a type
Python no longer knows raises on load, and the Tasks tab, rerun and attribution
all read those rows.

Deleting rows and narrowing the column in one migration is deliberate. Run
either half alone and the database is inconsistent with the code: rows without
the enum members break reads, and the narrowed column without the deletions
would reject nothing but leaves rows nothing can load.

Revision ID: 423d723b9e85
Revises: fc41fce7ba4b
Create Date: 2026-08-21 08:11:08.990988

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = '423d723b9e85'
down_revision: Union[str, None] = 'fc41fce7ba4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SUPERSEDED = (
    'PAPER_CLASSIFIER',
    'VARIANT_EXTRACTION',
    'PEDIGREE_DESCRIPTION',
    'PATIENT_EXTRACTION',
    'PATIENT_DEMOGRAPHICS',
    'PHENOTYPE_EXTRACTION',
    'PATIENT_VARIANT_OCCURRENCES',
    'COMPOUND_HET_EVALUATION',
    'SEGREGATION_EVIDENCE_EXTRACTION',
)

_REMAINING = (
    'PDF_PARSING',
    'GENERAL_PAPER_QUESTION',
    'PAPER_METADATA',
    'SEGREGATION_ANALYSIS_COMPUTED',
    'VARIANT_HARMONIZATION',
    'VARIANT_ANNOTATION',
    'HPO_LINKING',
    'MONDO_LINKING',
    'PAPER_EXTRACTION',
)


def upgrade() -> None:
    connection = op.get_bind()

    # Rows first: the batch alter below drops and recreates the table, so
    # deleting afterwards would mean recreating it around rows the new column
    # definition does not describe.
    placeholders = ', '.join(f"'{name}'" for name in SUPERSEDED)
    result = connection.execute(
        text(f'DELETE FROM tasks WHERE type IN ({placeholders})')  # noqa: S608
    )
    print(f'removed {result.rowcount} task rows of superseded types')

    # Nothing references tasks as a parent, so recreating it cascades to
    # nothing -- but the project pattern is to disable foreign keys around any
    # batch alter, and tasks carries CASCADE keys of its own.
    connection.execute(text('PRAGMA foreign_keys = OFF'))
    try:
        with op.batch_alter_table('tasks', schema=None) as batch_op:
            batch_op.alter_column(
                'type',
                existing_type=sa.VARCHAR(length=31),
                type_=sa.Enum(*_REMAINING, name='tasktype'),
                existing_nullable=False,
            )
    finally:
        connection.execute(text('PRAGMA foreign_keys = ON'))


def downgrade() -> None:
    # The rows cannot come back -- this widens the column so the old members
    # would be storable again, nothing more.
    connection = op.get_bind()
    connection.execute(text('PRAGMA foreign_keys = OFF'))
    try:
        with op.batch_alter_table('tasks', schema=None) as batch_op:
            batch_op.alter_column(
                'type',
                existing_type=sa.Enum(*_REMAINING, name='tasktype'),
                type_=sa.VARCHAR(length=31),
                existing_nullable=False,
            )
    finally:
        connection.execute(text('PRAGMA foreign_keys = ON'))
