"""split paper extraction into per-pass task types

PAPER_EXTRACTION ran five model calls inside one task row. Each is now its own
task, so the queue can retry, rerun and time them separately, and each later
pass is handed database ids rather than positions in a list.

The old rows must go before the enum changes: SQLEnum stores member names, so a
row naming a type Python no longer knows raises on load, and the Tasks tab,
rerun and attribution all read those rows. They cannot be rewritten into one of
the new types either -- no single pass is what a PAPER_EXTRACTION row recorded.

Deleting rows and changing the column in one migration is deliberate, following
423d723b9e85: run either half alone and the database is inconsistent with the
code.

Revision ID: 8f2a1c6d4e90
Revises: 7c1e4a2b8d33
Create Date: 2026-08-21 13:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = '8f2a1c6d4e90'
down_revision: Union[str, None] = '7c1e4a2b8d33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SHARED = (
    'PDF_PARSING',
    'GENERAL_PAPER_QUESTION',
    'PAPER_METADATA',
    'SEGREGATION_ANALYSIS_COMPUTED',
    'VARIANT_HARMONIZATION',
    'VARIANT_ANNOTATION',
    'HPO_LINKING',
    'MONDO_LINKING',
)
_BEFORE = (*_SHARED, 'PAPER_EXTRACTION')
_AFTER = (
    *_SHARED,
    'PEDIGREE_IDENTIFICATION',
    'PAPER_STRUCTURE',
    'PATIENT_DETAILS',
    'PATIENT_GENOTYPES',
    'SEGREGATION_EVIDENCE',
)


def _swap(before: tuple[str, ...], after: tuple[str, ...]) -> None:
    connection = op.get_bind()

    # Rows first: the batch alter below drops and recreates the table, so
    # deleting afterwards would mean recreating it around rows the new column
    # definition does not describe.
    gone = set(before) - set(after)
    placeholders = ', '.join(f"'{name}'" for name in sorted(gone))
    result = connection.execute(
        text(f'DELETE FROM tasks WHERE type IN ({placeholders})')  # noqa: S608
    )
    print(f'removed {result.rowcount} task rows of retired types')

    # tasks carries CASCADE keys of its own, so foreign keys go off around the
    # batch alter as the project pattern requires.
    connection.execute(text('PRAGMA foreign_keys = OFF'))
    try:
        with op.batch_alter_table('tasks', schema=None) as batch_op:
            batch_op.alter_column(
                'type',
                existing_type=sa.Enum(*before, name='tasktype'),
                type_=sa.Enum(*after, name='tasktype'),
                existing_nullable=False,
            )
    finally:
        connection.execute(text('PRAGMA foreign_keys = ON'))


def upgrade() -> None:
    _swap(_BEFORE, _AFTER)


def downgrade() -> None:
    # The pass rows cannot be merged back into one PAPER_EXTRACTION row, so
    # they are dropped the same way the upgrade drops what it replaces.
    _swap(_AFTER, _BEFORE)
