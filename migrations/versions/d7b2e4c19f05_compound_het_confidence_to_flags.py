"""compound-het confidence tier becomes a curator flag

A compound-het pairing used to carry a confidence of confirmed / assumed /
uncertain, shown as a badge on the occurrence row. The flags table now does
that job for every agent: a pairing the paper only suggests is output and
flagged, and the pair itself keeps just its reasoning. This migration

* raises one flag per existing assumed or uncertain pair (linked to both
  halves, the lower-id one first, plus its patient and variant) so nothing
  a curator was shown disappears from the review;
* rewrites every pairing's reasoning block from ``{value: <tier>, ...}`` to
  ``{value: true, ...}`` (ReasoningBlock[bool]: the pair is compound het);
* renames the edits history for manual pairings from
  ``paired_variant_confidence`` to ``paired_variant``, the field name the
  API records now;
* drops ``paired_variant_confidence`` and renames
  ``paired_variant_confidence_reasoning`` to ``paired_variant_reasoning``.

An extraction snapshot taken before this migration still restores (the
dropped column is skipped, the renamed one is not recognised), so a reset
to such a snapshot leaves its pairings without reasoning.

Revision ID: d7b2e4c19f05
Revises: c4e1f7a92b63
Create Date: 2026-10-14 12:00:00.000000

"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd7b2e4c19f05'
down_revision: Union[str, None] = 'c4e1f7a92b63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SOURCE = 'COMPOUND_HET_EVALUATION'


def _label(variant_evidence: object) -> str:
    if isinstance(variant_evidence, str):
        try:
            variant_evidence = json.loads(variant_evidence)
        except ValueError:
            return 'a variant'
    if isinstance(variant_evidence, dict) and variant_evidence.get('value'):
        return str(variant_evidence['value'])
    return 'a variant'


def _flag_existing_uncertain_pairs(connection: sa.Connection) -> None:
    rows = connection.execute(
        sa.text(
            'SELECT o.id, o.paper_id, o.patient_id, o.variant_id, '
            'o.paired_variant_link_id, o.paired_variant_confidence, '
            'o.paired_variant_confidence_reasoning, '
            'v.variant_evidence AS own_label, p.variant_evidence AS partner_label '
            'FROM patient_variant_occurrences o '
            'JOIN variants v ON v.id = o.variant_id '
            'LEFT JOIN patient_variant_occurrences q '
            'ON q.id = o.paired_variant_link_id '
            'LEFT JOIN variants p ON p.id = q.variant_id '
            "WHERE o.paired_variant_confidence IN ('assumed', 'uncertain')"
        )
    ).mappings()
    for row in rows:
        partner = row['paired_variant_link_id']
        # One flag per pair, on the lower-id half.
        if partner is not None and partner < row['id']:
            continue
        reasoning = row['paired_variant_confidence_reasoning']
        if isinstance(reasoning, str):
            try:
                reasoning = json.loads(reasoning)
            except ValueError:
                reasoning = None
        why = (
            reasoning.get('reasoning') if isinstance(reasoning, dict) else None
        ) or 'No reasoning was recorded for this pairing.'
        subject = (
            f'Compound het pair taken as {row["paired_variant_confidence"]}: '
            f'{_label(row["own_label"])} with {_label(row["partner_label"])}'
        )
        connection.execute(
            sa.text(
                'INSERT INTO flags (paper_id, patient_id, variant_id, '
                'occurrence_id, paired_occurrence_id, source, kind, subject, '
                'evidence) '
                'VALUES (:paper_id, :patient_id, :variant_id, :occurrence_id, '
                ':paired_occurrence_id, :source, :kind, :subject, :evidence)'
            ),
            {
                'paper_id': row['paper_id'],
                'patient_id': row['patient_id'],
                'variant_id': row['variant_id'],
                'occurrence_id': row['id'],
                'paired_occurrence_id': partner,
                'source': _SOURCE,
                # An 'assumed' pair rested on an inference (segregation, one
                # parent's genotype); an 'uncertain' one on a reading the
                # paper leaves open.
                'kind': 'inferred'
                if row['paired_variant_confidence'] == 'assumed'
                else 'ambiguous',
                'subject': subject,
                'evidence': json.dumps({'value': subject, 'reasoning': why}),
            },
        )


def upgrade() -> None:
    connection = op.get_bind()

    _flag_existing_uncertain_pairs(connection)
    connection.execute(
        sa.text(
            'UPDATE patient_variant_occurrences '
            'SET paired_variant_confidence_reasoning = json_set('
            "paired_variant_confidence_reasoning, '$.value', json('true')) "
            'WHERE paired_variant_confidence_reasoning IS NOT NULL'
        )
    )
    connection.execute(
        sa.text(
            "UPDATE edits SET field_name = 'paired_variant' "
            "WHERE field_name = 'paired_variant_confidence'"
        )
    )

    # patient_variant_occurrences has CASCADE dependents (flags, and its own
    # paired_variant_link_id); batch_alter_table recreates the table, which
    # fires those with foreign keys on. PRAGMA is a no-op inside alembic's
    # transaction, hence autocommit_block (see CLAUDE.md).
    with op.get_context().autocommit_block():
        connection.exec_driver_sql('PRAGMA foreign_keys = OFF')
    try:
        with op.batch_alter_table(
            'patient_variant_occurrences', schema=None
        ) as batch_op:
            batch_op.drop_column('paired_variant_confidence')
            batch_op.alter_column(
                'paired_variant_confidence_reasoning',
                new_column_name='paired_variant_reasoning',
            )
    finally:
        with op.get_context().autocommit_block():
            connection.exec_driver_sql('PRAGMA foreign_keys = ON')


def downgrade() -> None:
    connection = op.get_bind()
    with op.get_context().autocommit_block():
        connection.exec_driver_sql('PRAGMA foreign_keys = OFF')
    try:
        with op.batch_alter_table(
            'patient_variant_occurrences', schema=None
        ) as batch_op:
            batch_op.alter_column(
                'paired_variant_reasoning',
                new_column_name='paired_variant_confidence_reasoning',
            )
            batch_op.add_column(
                sa.Column('paired_variant_confidence', sa.String(), nullable=True)
            )
    finally:
        with op.get_context().autocommit_block():
            connection.exec_driver_sql('PRAGMA foreign_keys = ON')

    # The tiers cannot be recovered; every surviving pair reads as confirmed.
    connection.execute(
        sa.text(
            'UPDATE patient_variant_occurrences '
            "SET paired_variant_confidence = 'confirmed', "
            'paired_variant_confidence_reasoning = json_set('
            "paired_variant_confidence_reasoning, '$.value', 'confirmed') "
            'WHERE paired_variant_confidence_reasoning IS NOT NULL'
        )
    )
    connection.execute(
        sa.text(
            "UPDATE edits SET field_name = 'paired_variant_confidence' "
            "WHERE field_name = 'paired_variant'"
        )
    )
    connection.execute(
        sa.text('DELETE FROM flags WHERE source = :source'), {'source': _SOURCE}
    )
