"""add is_paper_relevant_evidence

Paper relevance is judged by the single-pass extraction now. Its reasoning was
being written into section_classifications, the column the deleted section
classifier used to fill, because that was the only JSON column on papers. Give
it a column of its own and move what is already there.

The column is added with a plain ALTER TABLE ADD COLUMN rather than a batch
operation. papers has eight tables cascading off it -- pedigrees, conversations,
patient_variant_occurrences, families, variants, phenotypes, tasks and patients
-- so rebuilding it is the exact shape of the June migration that emptied the
patients table. Adding a column needs no rebuild, so none is done.

section_classifications is left in place. Nothing writes it any more, but
dropping it would rebuild papers, and a dead column is a much smaller problem
than that risk.

Revision ID: 7c1e4a2b8d33
Revises: 423d723b9e85
Create Date: 2026-08-21 09:02:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = '7c1e4a2b8d33'
down_revision: Union[str, None] = '423d723b9e85'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'papers',
        sa.Column('is_paper_relevant_evidence', sa.JSON(), nullable=True),
    )

    # Carry over the relevance block the classifier left behind, so papers
    # judged before this keep their explanation in the UI.
    connection = op.get_bind()
    result = connection.execute(
        text("""
            UPDATE papers
               SET is_paper_relevant_evidence =
                   json_extract(section_classifications, '$.is_paper_relevant')
             WHERE section_classifications IS NOT NULL
               AND json_extract(section_classifications, '$.is_paper_relevant')
                   IS NOT NULL
        """)
    )
    print(f'carried over {result.rowcount} relevance blocks')


def downgrade() -> None:
    op.drop_column('papers', 'is_paper_relevant_evidence')
