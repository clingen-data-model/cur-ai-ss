"""Occurrences get an origin column; de_novo folds into it

The per-occurrence ``inheritance`` column holds a mode of inheritance
(Dominant, Recessive, ...) while papers mostly use the word for which
parent a variant came from, and the agent had nowhere to put that fact but
the reasoning text. Curators reported the two being confused on 2026-10-26;
on dev-caa 232 of 866 occurrence reasonings named a parent, mapped to a
mode inconsistently even within one paper. ``origin`` (Maternal, Paternal,
Both parents, De novo, Inherited (parent not stated), Unknown) gives that
fact a field; the ``de_novo`` boolean, which was one value of it, goes.

Backfill: a de novo row becomes ``origin = 'De novo'`` and every other row
``'Unknown'``; the de_novo evidence block carries over as the origin
evidence with its value replaced, so no reasoning is lost. A parent named
only in that reasoning stays Unknown until Patient Variant Occurrences is
re-run (``lib.bin.requeue_papers --from-task 'Patient Variant Occurrences'
--all``), which is the real backfill.

Native ALTER TABLE ADD COLUMN and DROP COLUMN (SQLite 3.35+; dev-caa runs
3.45), not a batch rewrite: the table has CASCADE dependents (flags, edits,
tasks, its own pairing FK), and the CLAUDE.md caveat applies to batch mode.
The dropped columns are unindexed and unconstrained, which the native form
requires. Both new columns get a server default so a snapshot from before
this migration still restores (lib.misc.snapshots._coerce_row).

Revision ID: a4e7c2d9f1b3
Revises: 7c1e5a9d3b2f
Create Date: 2026-10-26 16:00:00.000000

"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a4e7c2d9f1b3'
down_revision: Union[str, None] = '7c1e5a9d3b2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = 'patient_variant_occurrences'
_NOT_EXTRACTED = json.dumps(
    {
        'value': 'Unknown',
        'reasoning': (
            'Not extracted: this run predates the origin field. Re-run Patient '
            'Variant Occurrences to fill it.'
        ),
        'citations': [],
    }
)


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column('origin', sa.String(), nullable=False, server_default='Unknown'),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            'origin_evidence',
            sa.JSON(),
            nullable=False,
            server_default=_NOT_EXTRACTED,
        ),
    )
    op.execute(
        f"""
        UPDATE {_TABLE} SET
            origin = CASE WHEN de_novo THEN 'De novo' ELSE 'Unknown' END,
            origin_evidence = json_set(
                de_novo_evidence, '$.value',
                CASE WHEN de_novo THEN 'De novo' ELSE 'Unknown' END
            )
        """
    )
    op.drop_column(_TABLE, 'de_novo')
    op.drop_column(_TABLE, 'de_novo_evidence')


def downgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column('de_novo', sa.Boolean(), nullable=False, server_default='0'),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            'de_novo_evidence',
            sa.JSON(),
            nullable=False,
            server_default=json.dumps(
                {'value': False, 'reasoning': 'Not extracted.', 'citations': []}
            ),
        ),
    )
    op.execute(
        f"""
        UPDATE {_TABLE} SET
            de_novo = CASE WHEN origin = 'De novo' THEN 1 ELSE 0 END,
            de_novo_evidence = json_set(
                origin_evidence, '$.value',
                CASE WHEN origin = 'De novo' THEN json('true') ELSE json('false') END
            )
        """
    )
    op.drop_column(_TABLE, 'origin')
    op.drop_column(_TABLE, 'origin_evidence')
