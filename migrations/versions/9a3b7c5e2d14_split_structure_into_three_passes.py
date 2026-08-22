"""split the structure pass into classifier, patients and variants

One response was carrying the classification, the patient roster and the
variants. On a cohort paper that is the largest thing the pipeline asks for --
paper 92 has twenty-three patients in one table and eleven variants -- and it
began producing the classification and stopping: the relevance reasoning named
the table that the same response then returned no rows from. Three responses
now, each with one job, and they run concurrently off PDF_PARSING.

The names are the ones the pre-split pipeline used, so the Tasks tab and the
rerun controls read the way curators are used to. That also means this
migration reintroduces PATIENT_EXTRACTION, VARIANT_EXTRACTION and the rest,
which 423d723b9e85 removed -- their old rows went with that migration, so
nothing stale can load under the new meaning.

Revision ID: 9a3b7c5e2d14
Revises: 8f2a1c6d4e90
Create Date: 2026-08-22 13:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = '9a3b7c5e2d14'
down_revision: Union[str, None] = '8f2a1c6d4e90'
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
_BEFORE = (
    *_SHARED,
    'PEDIGREE_IDENTIFICATION',
    'PAPER_STRUCTURE',
    'PATIENT_DETAILS',
    'PATIENT_GENOTYPES',
    'SEGREGATION_EVIDENCE',
)
_AFTER = (
    *_SHARED,
    'PEDIGREE_DESCRIPTION',
    'PAPER_CLASSIFIER',
    'PATIENT_EXTRACTION',
    'VARIANT_EXTRACTION',
    'PATIENT_DEMOGRAPHICS',
    'PATIENT_VARIANT_OCCURRENCES',
    'SEGREGATION_EVIDENCE_EXTRACTION',
)


def _swap(before: tuple[str, ...], after: tuple[str, ...]) -> None:
    connection = op.get_bind()

    # Rows first: the batch alter drops and recreates the table, so deleting
    # afterwards would mean recreating it around rows the new column definition
    # does not describe. Every retired name is renamed rather than mapped
    # across -- PAPER_STRUCTURE became three tasks, so no single successor is
    # what one of its rows recorded.
    gone = set(before) - set(after)
    placeholders = ', '.join(f"'{name}'" for name in sorted(gone))
    result = connection.execute(
        text(f'DELETE FROM tasks WHERE type IN ({placeholders})')  # noqa: S608
    )
    print(f'removed {result.rowcount} task rows of retired types')

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
    _swap(_AFTER, _BEFORE)
