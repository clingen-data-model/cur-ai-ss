"""tasks.type: PEDIGREE_DESCRIPTION becomes FIGURE_DESCRIPTION

The step that finds and describes the pedigree figure is growing into one
that describes every figure extraction can read (pedigrees, chromatograms,
gels, copy-number plots, read pileups, karyotypes), so the task type is
renamed first. SQLEnum columns store the member's *name* (see CLAUDE.md), so
every existing row must be rewritten or the ORM raises LookupError on the
first read of the tasks table.

Plain UPDATEs, no DDL: tasks.type is a VARCHAR with no CHECK constraint.
Snapshot files store the member's *value* ('Pedigree Description');
lib.misc.snapshots maps that old value on restore, so they are left alone.

Revision ID: a3f9c2e7d1b4
Revises: e8c3a5d1f7b2
Create Date: 2026-10-21 18:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a3f9c2e7d1b4'
down_revision: Union[str, None] = 'e8c3a5d1f7b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE tasks SET type = 'FIGURE_DESCRIPTION' "
        "WHERE type = 'PEDIGREE_DESCRIPTION'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE tasks SET type = 'PEDIGREE_DESCRIPTION' "
        "WHERE type = 'FIGURE_DESCRIPTION'"
    )
