"""repair inheritance_evidence blobs still holding 'De Novo'

Finishes the job c3d4e5f6a7b8 started. That migration removed 'De Novo' as an
Inheritance value and backfilled the two typed columns -- de_novo = 1,
inheritance = 'Unknown' -- but left inheritance_evidence untouched, because it
is a JSON blob rather than a column and so was invisible to a plain UPDATE of
enum-valued columns.

The blob is not free-form: PatientVariantOccurrenceResp types it as
HumanEvidenceBlock[Inheritance], so its `value` is validated against the same
enum on every read. Nine rows across eight papers therefore held a value that
had stopped being legal, and each one made GET /papers/{id}/occurrences raise
a pydantic ValidationError -- a 500 that took down the whole extraction page
for those papers. Written in July, first noticed in September, because nothing
reads the blob until someone opens the paper.

Lossless: quote and reasoning are preserved, and the de novo finding itself is
already carried by de_novo = 1, which c3d4e5f6a7b8 set on exactly these rows.

Pure data UPDATE -- no schema change and no batch_alter_table, so the
PRAGMA foreign_keys / autocommit_block dance CLAUDE.md requires for batch
alterations does not apply here.

Revision ID: d4f7a2b8c1e9
Revises: b7e4a1f92c3d
Create Date: 2026-09-18
"""

import sqlalchemy as sa
from alembic import op

revision = 'd4f7a2b8c1e9'
down_revision = 'b7e4a1f92c3d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            'UPDATE patient_variant_occurrences '
            "SET inheritance_evidence = json_set(inheritance_evidence, '$.value', 'Unknown') "
            "WHERE json_extract(inheritance_evidence, '$.value') = 'De Novo'"
        )
    )


def downgrade() -> None:
    # Deliberately empty, matching c3d4e5f6a7b8. Restoring 'De Novo' would write
    # back a value the Inheritance enum no longer accepts, recreating the 500
    # this migration exists to clear.
    pass
