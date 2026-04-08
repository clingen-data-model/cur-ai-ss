"""squashed initial schema with families, tasks, and variants improvements

Revision ID: 0001_squashed_initial_schema
Revises:
Create Date: 2026-04-08 00:00:00.000000

This migration combines the initial schema and all subsequent structural changes
up to but not including the upsert_gene_symbols migration.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0001_squashed_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # Create genes table
    op.create_table(
        'genes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('genes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_genes_symbol'), ['symbol'], unique=True)

    # Create papers table (without pipeline_status)
    op.create_table(
        'papers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('content_hash', sa.String(), nullable=False),
        sa.Column('gene_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('first_author', sa.String(), nullable=True),
        sa.Column('journal_name', sa.String(), nullable=True),
        sa.Column('abstract', sa.Text(), nullable=True),
        sa.Column('publication_year', sa.Integer(), nullable=True),
        sa.Column('doi', sa.String(), nullable=True),
        sa.Column('pmid', sa.String(), nullable=True),
        sa.Column('pmcid', sa.String(), nullable=True),
        sa.Column('paper_types', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['gene_id'], ['genes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_papers_content_hash'), ['content_hash'], unique=True
        )
        batch_op.create_index(
            batch_op.f('ix_papers_gene_id'), ['gene_id'], unique=False
        )

    # Create families table
    op.create_table(
        'families',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('identifier', sa.String(), nullable=False),
        sa.Column('identifier_evidence', sa.JSON(), nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_families_paper_id', 'families', ['paper_id'], unique=False)

    # Create patients table with family_id (CASCADE delete)
    op.create_table(
        'patients',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('family_id', sa.Integer(), nullable=False),
        sa.Column('identifier', sa.String(), nullable=False),
        sa.Column('proband_status', sa.String(), nullable=False),
        sa.Column('sex', sa.String(), nullable=False),
        sa.Column('age_diagnosis', sa.Integer(), nullable=True),
        sa.Column('age_report', sa.Integer(), nullable=True),
        sa.Column('age_death', sa.Integer(), nullable=True),
        sa.Column('country_of_origin', sa.String(), nullable=False),
        sa.Column('race_ethnicity', sa.String(), nullable=False),
        sa.Column('affected_status', sa.String(), nullable=False),
        sa.Column('identifier_evidence', sa.JSON(), nullable=False),
        sa.Column('proband_status_evidence', sa.JSON(), nullable=False),
        sa.Column('sex_evidence', sa.JSON(), nullable=False),
        sa.Column('age_diagnosis_evidence', sa.JSON(), nullable=False),
        sa.Column('age_report_evidence', sa.JSON(), nullable=False),
        sa.Column('age_death_evidence', sa.JSON(), nullable=False),
        sa.Column('country_of_origin_evidence', sa.JSON(), nullable=False),
        sa.Column('race_ethnicity_evidence', sa.JSON(), nullable=False),
        sa.Column('affected_status_evidence', sa.JSON(), nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['family_id'], ['families.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.create_index('ix_patients_paper_id', ['paper_id'], unique=False)
        batch_op.create_index('ix_patients_family_id', ['family_id'], unique=False)

    # Create pedigrees table
    op.create_table(
        'pedigrees',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('image_id', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('paper_id'),
        sa.UniqueConstraint('paper_id', 'image_id'),
    )
    with op.batch_alter_table('pedigrees', schema=None) as batch_op:
        batch_op.create_index('ix_pedigrees_paper_id', ['paper_id'], unique=False)

    # Create variants table with main_focus fields
    op.create_table(
        'variants',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('variant', sa.String(), nullable=True),
        sa.Column('transcript', sa.String(), nullable=True),
        sa.Column('protein_accession', sa.String(), nullable=True),
        sa.Column('genomic_accession', sa.String(), nullable=True),
        sa.Column('lrg_accession', sa.String(), nullable=True),
        sa.Column('gene_accession', sa.String(), nullable=True),
        sa.Column('genomic_coordinates', sa.String(), nullable=True),
        sa.Column('genome_build', sa.String(), nullable=True),
        sa.Column('rsid', sa.String(), nullable=True),
        sa.Column('caid', sa.String(), nullable=True),
        sa.Column('hgvs_c', sa.String(), nullable=True),
        sa.Column('hgvs_p', sa.String(), nullable=True),
        sa.Column('hgvs_g', sa.String(), nullable=True),
        sa.Column('variant_type', sa.String(), nullable=False),
        sa.Column('functional_evidence', sa.Boolean(), nullable=False),
        sa.Column('main_focus', sa.Boolean(), nullable=False),
        sa.Column('transcript_evidence', sa.JSON(), nullable=False),
        sa.Column('protein_accession_evidence', sa.JSON(), nullable=False),
        sa.Column('genomic_accession_evidence', sa.JSON(), nullable=False),
        sa.Column('lrg_accession_evidence', sa.JSON(), nullable=False),
        sa.Column('gene_accession_evidence', sa.JSON(), nullable=False),
        sa.Column('genomic_coordinates_evidence', sa.JSON(), nullable=False),
        sa.Column('genome_build_evidence', sa.JSON(), nullable=False),
        sa.Column('rsid_evidence', sa.JSON(), nullable=False),
        sa.Column('caid_evidence', sa.JSON(), nullable=False),
        sa.Column('variant_evidence', sa.JSON(), nullable=False),
        sa.Column('hgvs_c_evidence', sa.JSON(), nullable=False),
        sa.Column('hgvs_p_evidence', sa.JSON(), nullable=False),
        sa.Column('hgvs_g_evidence', sa.JSON(), nullable=False),
        sa.Column('variant_type_evidence', sa.JSON(), nullable=False),
        sa.Column('functional_evidence_evidence', sa.JSON(), nullable=False),
        sa.Column('main_focus_evidence', sa.JSON(), nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('variants', schema=None) as batch_op:
        batch_op.create_index('ix_variants_paper_id', ['paper_id'], unique=False)

    # Create phenotypes table
    op.create_table(
        'phenotypes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('concept', sa.String(), nullable=False),
        sa.Column('concept_evidence', sa.JSON(), nullable=False),
        sa.Column('negated', sa.Boolean(), nullable=False),
        sa.Column('uncertain', sa.Boolean(), nullable=False),
        sa.Column('family_history', sa.Boolean(), nullable=False),
        sa.Column('onset', sa.String(), nullable=True),
        sa.Column('location', sa.String(), nullable=True),
        sa.Column('severity', sa.String(), nullable=True),
        sa.Column('modifier', sa.String(), nullable=True),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('phenotypes', schema=None) as batch_op:
        batch_op.create_index('ix_phenotypes_paper_id', ['paper_id'], unique=False)
        batch_op.create_index('ix_phenotypes_patient_id', ['patient_id'], unique=False)

    # Create harmonized_variants table
    op.create_table(
        'harmonized_variants',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('variant_id', sa.Integer(), nullable=False),
        sa.Column('gnomad_style_coordinates', sa.String(), nullable=True),
        sa.Column('rsid', sa.String(), nullable=True),
        sa.Column('caid', sa.String(), nullable=True),
        sa.Column('hgvs_c', sa.String(), nullable=True),
        sa.Column('hgvs_p', sa.String(), nullable=True),
        sa.Column('hgvs_g', sa.String(), nullable=True),
        sa.Column('reasoning', sa.String(), nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('variant_id', name='uq_harmonized_variants_variant_id'),
    )
    with op.batch_alter_table('harmonized_variants', schema=None) as batch_op:
        batch_op.create_index(
            'ix_harmonized_variants_variant_id', ['variant_id'], unique=False
        )

    # Create patient_variant_links table
    op.create_table(
        'patient_variant_links',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('variant_id', sa.Integer(), nullable=False),
        sa.Column('zygosity', sa.String(), nullable=False),
        sa.Column('inheritance', sa.String(), nullable=False),
        sa.Column('testing_methods', sa.JSON(), nullable=False),
        sa.Column('zygosity_evidence', sa.JSON(), nullable=False),
        sa.Column('inheritance_evidence', sa.JSON(), nullable=False),
        sa.Column('testing_methods_evidence', sa.JSON(), nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'patient_id', 'variant_id', name='uq_patient_variant_links_patient_variant'
        ),
    )
    with op.batch_alter_table('patient_variant_links', schema=None) as batch_op:
        batch_op.create_index(
            'ix_patient_variant_links_patient_id', ['patient_id'], unique=False
        )
        batch_op.create_index(
            'ix_patient_variant_links_variant_id', ['variant_id'], unique=False
        )

    # Create enriched_variants table
    op.create_table(
        'enriched_variants',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('harmonized_variant_id', sa.Integer(), nullable=False),
        sa.Column('pathogenicity', sa.String(), nullable=True),
        sa.Column('submissions', sa.Integer(), nullable=True),
        sa.Column('stars', sa.Integer(), nullable=True),
        sa.Column('exon', sa.String(), nullable=True),
        sa.Column('revel', sa.Float(), nullable=True),
        sa.Column('alphamissense_class', sa.String(), nullable=True),
        sa.Column('alphamissense_score', sa.Float(), nullable=True),
        sa.Column('spliceai', sa.JSON(), nullable=True),
        sa.Column('gnomad_style_coordinates', sa.String(), nullable=True),
        sa.Column('rsid', sa.String(), nullable=True),
        sa.Column('caid', sa.String(), nullable=True),
        sa.Column('gnomad_top_level_af', sa.Float(), nullable=True),
        sa.Column('gnomad_popmax_af', sa.Float(), nullable=True),
        sa.Column('gnomad_popmax_population', sa.String(), nullable=True),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['harmonized_variant_id'], ['harmonized_variants.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'harmonized_variant_id', name='uq_enriched_variants_harmonized_variant_id'
        ),
    )
    with op.batch_alter_table('enriched_variants', schema=None) as batch_op:
        batch_op.create_index(
            'ix_enriched_variants_harmonized_variant_id',
            ['harmonized_variant_id'],
            unique=False,
        )

    # Create hpos table with 'reasoning' column (renamed from hpo_reasoning)
    op.create_table(
        'hpos',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('phenotype_id', sa.Integer(), nullable=False),
        sa.Column('hpo_id', sa.String(), nullable=True),
        sa.Column('hpo_name', sa.String(), nullable=True),
        sa.Column('reasoning', sa.String(), nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['phenotype_id'], ['phenotypes.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('phenotype_id', name='uq_hpos_phenotype_id'),
    )

    # Create tasks table
    op.create_table(
        'tasks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column(
            'type',
            sa.Enum(
                'PDF Parsing',
                'Paper Metadata',
                'Variant Extraction',
                'Pedigree Description',
                'Patient Extraction',
                'Variant Harmonization',
                'Variant Enrichment',
                'Patient Variant Linking',
                'Phenotype Extraction',
                'HPO Linking',
                name='tasktype',
            ),
            nullable=False,
        ),
        sa.Column('patient_id', sa.Integer(), nullable=True),
        sa.Column('variant_id', sa.Integer(), nullable=True),
        sa.Column('phenotype_id', sa.Integer(), nullable=True),
        sa.Column(
            'status',
            sa.Enum('Pending', 'Running', 'Completed', 'Failed', name='taskstatus'),
            nullable=False,
        ),
        sa.Column('tries', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.String(), nullable=True),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['phenotype_id'], ['phenotypes.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_tasks_paper_id', 'tasks', ['paper_id'], unique=False)
    op.create_index('ix_tasks_patient_id', 'tasks', ['patient_id'], unique=False)
    op.create_index('ix_tasks_phenotype_id', 'tasks', ['phenotype_id'], unique=False)
    op.create_index('ix_tasks_status', 'tasks', ['status'], unique=False)
    op.create_index('ix_tasks_type', 'tasks', ['type'], unique=False)
    op.create_index('ix_tasks_variant_id', 'tasks', ['variant_id'], unique=False)
    op.create_index(
        'ix_tasks_paper_id_status', 'tasks', ['paper_id', 'status'], unique=False
    )
    op.create_index(
        'ix_tasks_dedup',
        'tasks',
        ['type', 'paper_id', 'patient_id', 'variant_id', 'phenotype_id'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_tasks_dedup', table_name='tasks')
    op.drop_index('ix_tasks_paper_id_status', table_name='tasks')
    op.drop_index('ix_tasks_variant_id', table_name='tasks')
    op.drop_index('ix_tasks_type', table_name='tasks')
    op.drop_index('ix_tasks_status', table_name='tasks')
    op.drop_index('ix_tasks_phenotype_id', table_name='tasks')
    op.drop_index('ix_tasks_patient_id', table_name='tasks')
    op.drop_index('ix_tasks_paper_id', table_name='tasks')
    op.drop_table('tasks')

    op.drop_table('hpos')

    with op.batch_alter_table('enriched_variants', schema=None) as batch_op:
        batch_op.drop_index('ix_enriched_variants_harmonized_variant_id')

    op.drop_table('enriched_variants')

    with op.batch_alter_table('patient_variant_links', schema=None) as batch_op:
        batch_op.drop_index('ix_patient_variant_links_variant_id')
        batch_op.drop_index('ix_patient_variant_links_patient_id')

    op.drop_table('patient_variant_links')

    with op.batch_alter_table('harmonized_variants', schema=None) as batch_op:
        batch_op.drop_index('ix_harmonized_variants_variant_id')

    op.drop_table('harmonized_variants')

    with op.batch_alter_table('phenotypes', schema=None) as batch_op:
        batch_op.drop_index('ix_phenotypes_patient_id')
        batch_op.drop_index('ix_phenotypes_paper_id')

    op.drop_table('phenotypes')

    with op.batch_alter_table('variants', schema=None) as batch_op:
        batch_op.drop_index('ix_variants_paper_id')

    op.drop_table('variants')

    with op.batch_alter_table('pedigrees', schema=None) as batch_op:
        batch_op.drop_index('ix_pedigrees_paper_id')

    op.drop_table('pedigrees')

    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.drop_index('ix_patients_family_id')
        batch_op.drop_index('ix_patients_paper_id')

    op.drop_table('patients')

    op.drop_index('ix_families_paper_id', table_name='families')
    op.drop_table('families')

    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_papers_gene_id'))
        batch_op.drop_index(batch_op.f('ix_papers_content_hash'))

    op.drop_table('papers')

    with op.batch_alter_table('genes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_genes_symbol'))

    op.drop_table('genes')
