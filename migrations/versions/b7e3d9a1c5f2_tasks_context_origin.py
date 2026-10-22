"""tasks.context_origin: where a task's additional_context came from

A curator's note on a re-run (tasks.additional_context) now comes down the
successor graph to every descendant of that run (lib/tasks/misc.py,
enqueue_successors). A descendant must know it inherited the note, since an
inherited note starts a fresh run with the note in its first message rather
than a follow-up turn in a conversation whose inputs just changed, and the
message names the step the note was given to. ``context_origin`` holds that
step's task type; NULL means the note was given to the task itself, as every
existing note was.

A plain ADD COLUMN, nullable with no default: no batch alteration, so the
CASCADE caveat in CLAUDE.md does not apply. The column is a SQLEnum like
``tasks.type`` and so stores the member's *name* ('PATIENT_EXTRACTION'), not
its value.

Revision ID: b7e3d9a1c5f2
Revises: c4d8e1f2a9b7
Create Date: 2026-10-22 18:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7e3d9a1c5f2'
down_revision: Union[str, None] = 'c4d8e1f2a9b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TASK_TYPE_NAMES = (
    'PDF_PARSING',
    'PAPER_CLASSIFIER',
    'PAPER_METADATA',
    'VARIANT_EXTRACTION',
    'FIGURE_DESCRIPTION',
    'PATIENT_EXTRACTION',
    'PATIENT_DEMOGRAPHICS',
    'SEGREGATION_EVIDENCE_EXTRACTION',
    'SEGREGATION_ANALYSIS_COMPUTED',
    'VARIANT_HARMONIZATION',
    'VARIANT_ANNOTATION',
    'PATIENT_VARIANT_OCCURRENCES',
    'COMPOUND_HET_EVALUATION',
    'PHENOTYPE_EXTRACTION',
    'HPO_LINKING',
    'PAPER_MONDO_LINKING',
    'OCCURRENCE_MONDO_LINKING',
    'EXTRACTION_VERIFICATION',
)


def upgrade() -> None:
    op.add_column(
        'tasks',
        sa.Column(
            'context_origin',
            sa.Enum(*TASK_TYPE_NAMES, name='tasktype'),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('tasks', 'context_origin')
