"""tasks and flags: the three Patient task types become Individual

Curators have seen "Individual" for patient since 2026-11-06; the task types
were the one place the backend still named the step after the patient:
PATIENT_EXTRACTION, PATIENT_DEMOGRAPHICS and PATIENT_VARIANT_OCCURRENCES are
now INDIVIDUAL_EXTRACTION, INDIVIDUAL_DEMOGRAPHICS and
INDIVIDUAL_VARIANT_OCCURRENCES. SQLEnum columns store the member's *name*
(see CLAUDE.md), so every stored name is rewritten, or the ORM raises
LookupError on the first read: ``tasks.type``, ``tasks.context_origin`` and
``flags.source`` (a flag's source is the raising task type's name).

Plain UPDATEs, no DDL: the columns are VARCHARs with no CHECK constraint,
and the longest new name (30 characters) fits VARCHAR(31). Snapshot files
store the member's *value* ('Patient Extraction'); lib.misc.snapshots maps
the old values on restore, so they are left alone.

Revision ID: d5f1b3a7c9e2
Revises: c8e2a4f6b9d1
Create Date: 2026-11-12 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd5f1b3a7c9e2'
down_revision: Union[str, None] = 'c8e2a4f6b9d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RENAMES = {
    'PATIENT_EXTRACTION': 'INDIVIDUAL_EXTRACTION',
    'PATIENT_DEMOGRAPHICS': 'INDIVIDUAL_DEMOGRAPHICS',
    'PATIENT_VARIANT_OCCURRENCES': 'INDIVIDUAL_VARIANT_OCCURRENCES',
}

COLUMNS = [('tasks', 'type'), ('tasks', 'context_origin'), ('flags', 'source')]


def _rename(names: dict[str, str]) -> None:
    for table, column in COLUMNS:
        for old, new in names.items():
            op.execute(
                f"UPDATE {table} SET {column} = '{new}' WHERE {column} = '{old}'"
            )


def upgrade() -> None:
    _rename(RENAMES)


def downgrade() -> None:
    _rename({new: old for old, new in RENAMES.items()})
