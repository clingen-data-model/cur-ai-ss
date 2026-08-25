"""retire two task types and record why a paper was judged relevant

The reading pipeline was rebuilt to read the PDF itself rather than scrambled
markdown, and split so that no single response carries a whole curation. That
turned out to need almost nothing from the database: every task type it uses
already existed under the same name, because the split lands on the same
entities the original pipeline named. Patient Extraction is still patient
extraction.

Two types have no successor and their rows go:

  PHENOTYPE_EXTRACTION      phenotypes are returned with the patient they
                            belong to, by the demographics pass
  COMPOUND_HET_EVALUATION   pairing is decided with the genotypes that produce
                            it, in the occurrences pass

Rows of the other fifteen types are left alone. They describe work that still
means what it meant.

The rows must go because SQLEnum stores member names: a row naming a type
Python no longer knows raises on load, and the Tasks tab, rerun and attribution
all read those rows. The column itself needs no change -- SQLAlchemy's Enum
defaults to create_constraint=False, so on SQLite it is a plain VARCHAR sized to
the longest member, 31 characters before and after. Rebuilding the table to
rewrite VARCHAR(31) as VARCHAR(31) would be pure risk: tasks carries CASCADE
foreign keys, and a batch_alter_table on such a table is what emptied the
patients table in June.

Also adds papers.is_paper_relevant_evidence. Relevance used to be buried in
the classifier's section_classifications blob; it is a first-class judgement
with a reason a curator should see, so it gets a column, backfilled from the
blob.

Revision ID: c7f1a9b3e402
Revises: fc41fce7ba4b
Create Date: 2026-08-22 14:05:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = 'c7f1a9b3e402'
down_revision: Union[str, None] = 'fc41fce7ba4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RETIRED = ('PHENOTYPE_EXTRACTION', 'COMPOUND_HET_EVALUATION')


def upgrade() -> None:
    connection = op.get_bind()

    op.add_column(
        'papers',
        sa.Column('is_paper_relevant_evidence', sa.JSON(), nullable=True),
    )
    # Carry over the relevance block the classifier left behind, so papers
    # judged before this keep their explanation in the UI.
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

    placeholders = ', '.join(f"'{name}'" for name in RETIRED)
    result = connection.execute(
        text(f'DELETE FROM tasks WHERE type IN ({placeholders})')  # noqa: S608
    )
    print(f'removed {result.rowcount} task rows of retired types')


def downgrade() -> None:
    # The deleted rows cannot come back. The column stores whatever it is given,
    # so the retired members are storable again as soon as the code knows them.
    op.drop_column('papers', 'is_paper_relevant_evidence')
