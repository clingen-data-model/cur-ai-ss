"""add harmonized_variant_id to edits

Harmonized-variant fields (gnomad_style_coordinates, rsid, caid, hgvs_c/p/g)
had no edits-table column at all, so HarmonizedVariantUpdate.apply_to never
recorded an edit and EvidencePopover's "edited by curator" warning never had
anything to key off for the harmonization view -- the fix in this same change
makes apply_to record_edit() per changed field, keyed by harmonized_variant_id
rather than variant_id: harmonization can overwrite these fields wholesale on
a rerun, and the row is replaced in place rather than deleted/recreated (see
uq_harmonized_variants_variant_id), so history simply keeps accumulating
against that one row's own id the way the other FK columns here already
track the entity whose fields are actually being edited.

No data migration needed: this column has never existed, so there is no
existing history to repoint (unlike df75caa848cb's hpo_link_id backfill).

No PRAGMA foreign_keys dance needed: this only batch-alters edits (the child
side of every one of its FKs, same as af1cb1479ab0, 9aa984af2f96, and
df75caa848cb), and nothing else changes.

Revision ID: ae683ef42263
Revises: df75caa848cb
Create Date: 2026-09-24 10:55:17.414445

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'ae683ef42263'
down_revision: Union[str, None] = 'df75caa848cb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_CHECK = (
    '(patient_id IS NOT NULL) + (variant_id IS NOT NULL) + '
    '(occurrence_id IS NOT NULL) + (family_id IS NOT NULL) + '
    '(paper_id IS NOT NULL) + (segregation_evidence_id IS NOT NULL) + '
    '(phenotype_id IS NOT NULL) + (hpo_link_id IS NOT NULL) = 1'
)
_NEW_CHECK = (
    '(patient_id IS NOT NULL) + (variant_id IS NOT NULL) + '
    '(occurrence_id IS NOT NULL) + (family_id IS NOT NULL) + '
    '(paper_id IS NOT NULL) + (segregation_evidence_id IS NOT NULL) + '
    '(phenotype_id IS NOT NULL) + (hpo_link_id IS NOT NULL) + '
    '(harmonized_variant_id IS NOT NULL) = 1'
)


def upgrade() -> None:
    with op.batch_alter_table('edits', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('harmonized_variant_id', sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            'fk_edits_harmonized_variant_id_harmonized_variants',
            'harmonized_variants',
            ['harmonized_variant_id'],
            ['id'],
            ondelete='CASCADE',
        )
        batch_op.create_index(
            'ix_edits_harmonized_variant_id_field_name',
            ['harmonized_variant_id', 'field_name'],
        )
        batch_op.drop_constraint('ck_edits_exactly_one_entity', type_='check')
        batch_op.create_check_constraint('ck_edits_exactly_one_entity', _NEW_CHECK)


def downgrade() -> None:
    with op.batch_alter_table('edits', schema=None) as batch_op:
        batch_op.drop_constraint('ck_edits_exactly_one_entity', type_='check')
        batch_op.create_check_constraint('ck_edits_exactly_one_entity', _OLD_CHECK)
        batch_op.drop_index('ix_edits_harmonized_variant_id_field_name')
        batch_op.drop_constraint(
            'fk_edits_harmonized_variant_id_harmonized_variants', type_='foreignkey'
        )
        batch_op.drop_column('harmonized_variant_id')
