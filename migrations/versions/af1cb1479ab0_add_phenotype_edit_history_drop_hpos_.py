"""add phenotype edit history, drop hpos manually_linked

Phenotypes and their HPO links never got the edits-table treatment that
patients/variants/occurrences/families/papers/segregation_evidence got in
ab0eafbeac4f plus the record_edits()-at-creation calls added by e1617913.
This closes that gap: a phenotype_id FK column is added to edits, covering
both the phenotype's own concept field (field_name='concept') and its HPO
link (field_name='hpo') -- one column, not two, since a phenotype has at
most one HPO link and family_id already proves one FK column can carry
multiple field_names (identifier/consanguinity).

hpos.manually_linked becomes redundant the moment 'hpo' has a real edits row
to check instead, so it's dropped here too -- the app now derives
"manually linked" from edits-row presence rather than trusting a column that
would otherwise say the exact same thing forever.

Backfill has no real editor/timestamp to port (unlike 24aa340de723's
backfill, which had genuine edited_by_* JSON to copy from). Every
phenotypes row with manually_entered: true in concept_evidence, and every
hpos row with manually_linked = 1, gets one synthetic edits row instead:
user_id NULL, edited_at = that row's own updated_at. This isn't live
production history, so an approximate backfill is an accepted tradeoff.
Order matters: the boolean is read to build the backfill *before* its
column is dropped.

No PRAGMA foreign_keys dance needed anywhere in this migration:
- The edits batch_alter_table only adds a column/index and replaces its own
  CHECK constraint -- edits is the child side of every one of its FKs (see
  9aa984af2f96, which added two columns to edits the same way), so nothing
  CASCADEs onto edits.id and no implicit recreate can delete anything.
- Dropping hpos.manually_linked uses a plain op.drop_column, not
  batch_alter_table -- this SQLite version supports DROP COLUMN directly
  (see 24be132ecd9b's downgrade, which already does exactly this), and this
  migration gives nothing a CASCADE FK onto hpos.id, so there's no implicit
  recreate and no dependent to worry about either way.

Revision ID: af1cb1479ab0
Revises: cfdfbc016a3f
Create Date: 2026-09-23 20:02:18.527782

"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'af1cb1479ab0'
down_revision: Union[str, None] = 'cfdfbc016a3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_CHECK = (
    '(patient_id IS NOT NULL) + (variant_id IS NOT NULL) + '
    '(occurrence_id IS NOT NULL) + (family_id IS NOT NULL) + '
    '(paper_id IS NOT NULL) + (segregation_evidence_id IS NOT NULL) = 1'
)
_NEW_CHECK = (
    '(patient_id IS NOT NULL) + (variant_id IS NOT NULL) + '
    '(occurrence_id IS NOT NULL) + (family_id IS NOT NULL) + '
    '(paper_id IS NOT NULL) + (segregation_evidence_id IS NOT NULL) + '
    '(phenotype_id IS NOT NULL) = 1'
)


def upgrade() -> None:
    with op.batch_alter_table('edits', schema=None) as batch_op:
        batch_op.add_column(sa.Column('phenotype_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_edits_phenotype_id_phenotypes',
            'phenotypes',
            ['phenotype_id'],
            ['id'],
            ondelete='CASCADE',
        )
        batch_op.create_index(
            'ix_edits_phenotype_id_field_name', ['phenotype_id', 'field_name']
        )
        batch_op.drop_constraint('ck_edits_exactly_one_entity', type_='check')
        batch_op.create_check_constraint('ck_edits_exactly_one_entity', _NEW_CHECK)

    connection = op.get_bind()

    # Backfill 'concept' rows for phenotypes a curator created by hand.
    phenotype_rows = connection.execute(
        sa.text('SELECT id, concept_evidence, updated_at FROM phenotypes')
    ).fetchall()
    for phenotype_id, raw_evidence, updated_at in phenotype_rows:
        if not raw_evidence:
            continue
        if not json.loads(raw_evidence).get('manually_entered'):
            continue
        connection.execute(
            sa.text(
                'INSERT INTO edits (phenotype_id, field_name, user_id, edited_at) '
                "VALUES (:phenotype_id, 'concept', NULL, :edited_at)"
            ),
            {'phenotype_id': phenotype_id, 'edited_at': updated_at},
        )

    # Backfill 'hpo' rows for curator-linked HPO terms, read before the
    # column that carries this fact today is dropped below.
    hpo_rows = connection.execute(
        sa.text('SELECT phenotype_id, updated_at FROM hpos WHERE manually_linked = 1')
    ).fetchall()
    for phenotype_id, updated_at in hpo_rows:
        connection.execute(
            sa.text(
                'INSERT INTO edits (phenotype_id, field_name, user_id, edited_at) '
                "VALUES (:phenotype_id, 'hpo', NULL, :edited_at)"
            ),
            {'phenotype_id': phenotype_id, 'edited_at': updated_at},
        )

    op.drop_column('hpos', 'manually_linked')


def downgrade() -> None:
    op.add_column(
        'hpos',
        sa.Column('manually_linked', sa.Boolean(), server_default='0', nullable=False),
    )
    connection = op.get_bind()
    # Best-effort, matching 24aa340de723's documented asymmetry: restores the
    # boolean for phenotypes that have a 'hpo' edits row, whether this
    # migration's own backfill wrote it or real curator activity did
    # afterward -- it cannot tell those apart, which is fine, since both mean
    # the same thing this column ever meant.
    connection.execute(
        sa.text(
            'UPDATE hpos SET manually_linked = 1 WHERE phenotype_id IN '
            "(SELECT phenotype_id FROM edits WHERE field_name = 'hpo')"
        )
    )

    # Rows recording 'concept'/'hpo' history have nowhere to live once
    # phenotype_id is dropped below -- every other entity FK column on them
    # is NULL, which would violate ck_edits_exactly_one_entity the moment
    # SQLite recreates the table with the old (phenotype_id-less) check.
    # Not round-trippable, same as 24aa340de723's downgrade: a downgrade
    # followed by re-upgrading loses this history rather than duplicating it.
    connection.execute(sa.text('DELETE FROM edits WHERE phenotype_id IS NOT NULL'))

    with op.batch_alter_table('edits', schema=None) as batch_op:
        batch_op.drop_constraint('ck_edits_exactly_one_entity', type_='check')
        batch_op.create_check_constraint('ck_edits_exactly_one_entity', _OLD_CHECK)
        batch_op.drop_index('ix_edits_phenotype_id_field_name')
        batch_op.drop_constraint('fk_edits_phenotype_id_phenotypes', type_='foreignkey')
        batch_op.drop_column('phenotype_id')
