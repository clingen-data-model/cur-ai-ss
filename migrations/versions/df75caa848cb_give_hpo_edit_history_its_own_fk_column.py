"""give hpo edit history its own fk column

af1cb1479ab0 gave the phenotype's HPO link edit history (field_name='hpo')
the same phenotype_id FK column as its concept field, on the theory that a
phenotype has at most one HPO link so field_name alone disambiguates them --
mirroring how family_id already carries both 'identifier' and
'consanguinity'.

That theory missed a real difference: HpoDB rows are deleted and recreated
whenever HPO linking (re-)runs via the agent (see handle_hpo_linking), while
the parent phenotype is not. With 'hpo' edits keyed by phenotype_id, an
earlier curator relink's edit row survives the agent overwriting the link,
so manually_entered keeps reporting True for a term the agent just linked --
a stale-history bug, not a hypothetical one.

Giving hpo_link_id its own FK straight onto hpos.id fixes this structurally
rather than requiring every future HPO-link write path to remember to clean
up edits by hand: ON DELETE CASCADE retires an hpo edit row the instant the
link it describes is deleted, the same way every other entity's edit history
already works.

Data migration: every existing field_name='hpo' row (there can only be ones
this migration's own predecessor, af1cb1479ab0, backfilled or the app wrote
since) is repointed from phenotype_id to the matching hpos.id for that
phenotype. If no hpos row exists for that phenotype anymore (the link was
deleted after the edit was recorded), the edit row is dropped instead --
matching the CASCADE semantics this migration is putting in place.

No PRAGMA foreign_keys dance needed: this only batch-alters edits (the
child side of every one of its FKs, same as af1cb1479ab0 and 9aa984af2f96),
and nothing else changes.

Revision ID: df75caa848cb
Revises: af1cb1479ab0
Create Date: 2026-09-23 20:46:05.989259

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'df75caa848cb'
down_revision: Union[str, None] = 'af1cb1479ab0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_CHECK = (
    '(patient_id IS NOT NULL) + (variant_id IS NOT NULL) + '
    '(occurrence_id IS NOT NULL) + (family_id IS NOT NULL) + '
    '(paper_id IS NOT NULL) + (segregation_evidence_id IS NOT NULL) + '
    '(phenotype_id IS NOT NULL) = 1'
)
_NEW_CHECK = (
    '(patient_id IS NOT NULL) + (variant_id IS NOT NULL) + '
    '(occurrence_id IS NOT NULL) + (family_id IS NOT NULL) + '
    '(paper_id IS NOT NULL) + (segregation_evidence_id IS NOT NULL) + '
    '(phenotype_id IS NOT NULL) + (hpo_link_id IS NOT NULL) = 1'
)


def upgrade() -> None:
    with op.batch_alter_table('edits', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hpo_link_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_edits_hpo_link_id_hpos',
            'hpos',
            ['hpo_link_id'],
            ['id'],
            ondelete='CASCADE',
        )
        batch_op.create_index(
            'ix_edits_hpo_link_id_field_name', ['hpo_link_id', 'field_name']
        )
        batch_op.drop_constraint('ck_edits_exactly_one_entity', type_='check')
        batch_op.create_check_constraint('ck_edits_exactly_one_entity', _NEW_CHECK)

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            'SELECT id, phenotype_id FROM edits '
            "WHERE field_name = 'hpo' AND phenotype_id IS NOT NULL"
        )
    ).fetchall()
    for edit_id, phenotype_id in rows:
        hpo_id = connection.execute(
            sa.text('SELECT id FROM hpos WHERE phenotype_id = :phenotype_id'),
            {'phenotype_id': phenotype_id},
        ).scalar()
        if hpo_id is None:
            connection.execute(
                sa.text('DELETE FROM edits WHERE id = :id'), {'id': edit_id}
            )
        else:
            connection.execute(
                sa.text(
                    'UPDATE edits SET hpo_link_id = :hpo_id, phenotype_id = NULL '
                    'WHERE id = :id'
                ),
                {'hpo_id': hpo_id, 'id': edit_id},
            )


def downgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            'SELECT id, hpo_link_id FROM edits '
            "WHERE field_name = 'hpo' AND hpo_link_id IS NOT NULL"
        )
    ).fetchall()
    for edit_id, hpo_link_id in rows:
        phenotype_id = connection.execute(
            sa.text('SELECT phenotype_id FROM hpos WHERE id = :hpo_link_id'),
            {'hpo_link_id': hpo_link_id},
        ).scalar()
        if phenotype_id is None:
            connection.execute(
                sa.text('DELETE FROM edits WHERE id = :id'), {'id': edit_id}
            )
        else:
            connection.execute(
                sa.text(
                    'UPDATE edits SET phenotype_id = :phenotype_id, hpo_link_id = NULL '
                    'WHERE id = :id'
                ),
                {'phenotype_id': phenotype_id, 'id': edit_id},
            )

    with op.batch_alter_table('edits', schema=None) as batch_op:
        batch_op.drop_constraint('ck_edits_exactly_one_entity', type_='check')
        batch_op.create_check_constraint('ck_edits_exactly_one_entity', _OLD_CHECK)
        batch_op.drop_index('ix_edits_hpo_link_id_field_name')
        batch_op.drop_constraint('fk_edits_hpo_link_id_hpos', type_='foreignkey')
        batch_op.drop_column('hpo_link_id')
