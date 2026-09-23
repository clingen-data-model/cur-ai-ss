"""split MONDO_LINKING into PAPER_MONDO_LINKING / OCCURRENCE_MONDO_LINKING

Revision ID: 8f2c4a1d6e93
Revises: 4cd141cb67ae
Create Date: 2026-09-23 18:00:00.000000

MONDO_LINKING did two jobs under one TaskType: a single paper-level row
(patient_variant_occurrence_id IS NULL), reset in place -- not duplicated,
enqueue_task dedupes on scope -- by either of its two predecessors; and a
per-occurrence row, fanned out atomically and only ever created once, from
Patient Variant Occurrences. Sharing a type meant the paper-level row's
legitimate re-run (honest: the work really is being redone) landed in the same
bucket as the fan-out row count, so a paper-level reset looked like the
fan-out type's already-Completed rows suddenly reappearing pending. Splitting
them gives each its own row(s) and removes the last case where a task type's
completeness could flicker.

`tasks.type` has no CHECK constraint on SQLite (plain VARCHAR), so this is a
data-only backfill: no batch_alter_table, so none of the migration-safety
dance in CLAUDE.md applies here. Existing rows are re-typed by the same scope
column the runtime already dispatches on (_build_mondo_linking_target).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8f2c4a1d6e93'
down_revision: Union[str, None] = '4cd141cb67ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE tasks SET type = 'PAPER_MONDO_LINKING' "
            "WHERE type = 'MONDO_LINKING' AND patient_variant_occurrence_id IS NULL"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE tasks SET type = 'OCCURRENCE_MONDO_LINKING' "
            "WHERE type = 'MONDO_LINKING' AND patient_variant_occurrence_id IS NOT NULL"
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE tasks SET type = 'MONDO_LINKING' "
            "WHERE type IN ('PAPER_MONDO_LINKING', 'OCCURRENCE_MONDO_LINKING')"
        )
    )
