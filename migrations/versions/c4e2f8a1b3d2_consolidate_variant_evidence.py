"""consolidate_variant_evidence

Revision ID: c4e2f8a1b3d2
Revises: b24f2aba6b49
Create Date: 2026-03-24 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4e2f8a1b3d2'
down_revision: Union[str, None] = 'b24f2aba6b49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old evidence columns
    with op.batch_alter_table('extracted_variants', schema=None) as batch_op:
        batch_op.drop_column('variant_evidence_context')
        batch_op.drop_column('variant_reasoning')
        batch_op.drop_column('hgvs_c_evidence_context')
        batch_op.drop_column('hgvs_c_evidence_reasoning')
        batch_op.drop_column('hgvs_p_evidence_context')
        batch_op.drop_column('hgvs_p_evidence_reasoning')
        batch_op.drop_column('hgvs_g_evidence_context')
        batch_op.drop_column('hgvs_g_evidence_reasoning')
        batch_op.drop_column('variant_type_evidence_context')
        batch_op.drop_column('variant_type_reasoning')
        batch_op.drop_column('functional_evidence_evidence_context')
        batch_op.drop_column('functional_evidence_reasoning')

    # Add new evidence columns as JSON
    with op.batch_alter_table('extracted_variants', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'transcript_evidence', sa.JSON(), nullable=False, server_default='{}'
            )
        )
        batch_op.add_column(
            sa.Column(
                'protein_accession_evidence',
                sa.JSON(),
                nullable=False,
                server_default='{}',
            )
        )
        batch_op.add_column(
            sa.Column(
                'genomic_accession_evidence',
                sa.JSON(),
                nullable=False,
                server_default='{}',
            )
        )
        batch_op.add_column(
            sa.Column(
                'lrg_accession_evidence', sa.JSON(), nullable=False, server_default='{}'
            )
        )
        batch_op.add_column(
            sa.Column(
                'gene_accession_evidence',
                sa.JSON(),
                nullable=False,
                server_default='{}',
            )
        )
        batch_op.add_column(
            sa.Column(
                'genomic_coordinates_evidence',
                sa.JSON(),
                nullable=False,
                server_default='{}',
            )
        )
        batch_op.add_column(
            sa.Column(
                'genome_build_evidence', sa.JSON(), nullable=False, server_default='{}'
            )
        )
        batch_op.add_column(
            sa.Column('rsid_evidence', sa.JSON(), nullable=False, server_default='{}')
        )
        batch_op.add_column(
            sa.Column('caid_evidence', sa.JSON(), nullable=False, server_default='{}')
        )
        batch_op.add_column(
            sa.Column(
                'variant_evidence', sa.JSON(), nullable=False, server_default='{}'
            )
        )
        batch_op.add_column(
            sa.Column('hgvs_c_evidence', sa.JSON(), nullable=False, server_default='{}')
        )
        batch_op.add_column(
            sa.Column('hgvs_p_evidence', sa.JSON(), nullable=False, server_default='{}')
        )
        batch_op.add_column(
            sa.Column('hgvs_g_evidence', sa.JSON(), nullable=False, server_default='{}')
        )
        batch_op.add_column(
            sa.Column(
                'variant_type_evidence', sa.JSON(), nullable=False, server_default='{}'
            )
        )
        batch_op.add_column(
            sa.Column(
                'functional_evidence_evidence',
                sa.JSON(),
                nullable=False,
                server_default='{}',
            )
        )


def downgrade() -> None:
    # Drop new evidence columns
    with op.batch_alter_table('extracted_variants', schema=None) as batch_op:
        batch_op.drop_column('transcript_evidence')
        batch_op.drop_column('protein_accession_evidence')
        batch_op.drop_column('genomic_accession_evidence')
        batch_op.drop_column('lrg_accession_evidence')
        batch_op.drop_column('gene_accession_evidence')
        batch_op.drop_column('genomic_coordinates_evidence')
        batch_op.drop_column('genome_build_evidence')
        batch_op.drop_column('rsid_evidence')
        batch_op.drop_column('caid_evidence')
        batch_op.drop_column('variant_evidence')
        batch_op.drop_column('hgvs_c_evidence')
        batch_op.drop_column('hgvs_p_evidence')
        batch_op.drop_column('hgvs_g_evidence')
        batch_op.drop_column('variant_type_evidence')
        batch_op.drop_column('functional_evidence_evidence')

    # Recreate old evidence columns
    with op.batch_alter_table('extracted_variants', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('variant_evidence_context', sa.Text(), nullable=True)
        )
        batch_op.add_column(sa.Column('variant_reasoning', sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column('hgvs_c_evidence_context', sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('hgvs_c_evidence_reasoning', sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('hgvs_p_evidence_context', sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('hgvs_p_evidence_reasoning', sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('hgvs_g_evidence_context', sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('hgvs_g_evidence_reasoning', sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('variant_type_evidence_context', sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('variant_type_reasoning', sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('functional_evidence_evidence_context', sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('functional_evidence_reasoning', sa.Text(), nullable=False)
        )
