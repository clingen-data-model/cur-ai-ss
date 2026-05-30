"""squashed initial schema

Revision ID: 0001_squashed_initial_schema
Revises:
Create Date: 2026-05-29 00:00:00.000000

This migration squashes the entire schema through the renaming of
patient_variant_links to patient_variant_occurrences and enriched_variants
to annotated_variants.
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

    # Create agent_runs table
    op.create_table(
        'agent_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('git_hash', sa.String(40), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('model', sa.String(255), nullable=False, server_default='gpt-5-mini'),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_runs_git_hash', 'agent_runs', ['git_hash'])
    op.create_index('ix_agent_runs_updated_at', 'agent_runs', ['updated_at'])

    # Create papers table
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
        sa.Column(
            'supplement_format',
            sa.Enum('pdf', 'docx', 'xlsx', name='fileformat'),
            nullable=True,
        ),
        sa.Column(
            'tag',
            sa.Enum('TrainingSet', 'ValidationSet', name='papertag'),
            nullable=True,
        ),
        sa.Column('is_paper_relevant', sa.Boolean(), nullable=True),
        sa.Column('section_classifications', sa.JSON(), nullable=True),
        sa.Column('disease_name', sa.String(), nullable=True),
        sa.Column('disease_name_evidence', sa.JSON(), nullable=True),
        sa.Column('disease_inheritance_mode', sa.String(), nullable=True),
        sa.Column('disease_inheritance_mode_evidence', sa.JSON(), nullable=True),
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

    # Create patients table
    op.create_table(
        'patients',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('family_id', sa.Integer(), nullable=False),
        sa.Column('agent_run_id', sa.Integer(), nullable=False),
        sa.Column('identifier', sa.String(), nullable=False),
        sa.Column('proband_status', sa.String(), nullable=False),
        sa.Column('sex', sa.String(), nullable=False),
        sa.Column('age_diagnosis', sa.Integer(), nullable=True),
        sa.Column('age_report', sa.Integer(), nullable=True),
        sa.Column('age_death', sa.Integer(), nullable=True),
        sa.Column(
            'age_diagnosis_unit',
            sa.Enum('Years', 'Months', 'Days', name='ageunit'),
            nullable=True,
        ),
        sa.Column(
            'age_report_unit',
            sa.Enum('Years', 'Months', 'Days', name='ageunit'),
            nullable=True,
        ),
        sa.Column(
            'age_death_unit',
            sa.Enum('Years', 'Months', 'Days', name='ageunit'),
            nullable=True,
        ),
        sa.Column('country_of_origin', sa.String(), nullable=False),
        sa.Column('race_ethnicity', sa.String(), nullable=False),
        sa.Column('affected_status', sa.String(), nullable=False),
        sa.Column('is_obligate_carrier', sa.Boolean(), nullable=True),
        sa.Column('relationship_to_proband', sa.String(), nullable=True),
        sa.Column('twin_type', sa.String(), nullable=True),
        sa.Column('identifier_evidence', sa.JSON(), nullable=False),
        sa.Column('proband_status_evidence', sa.JSON(), nullable=False),
        sa.Column('sex_evidence', sa.JSON(), nullable=False),
        sa.Column('age_diagnosis_evidence', sa.JSON(), nullable=False),
        sa.Column('age_report_evidence', sa.JSON(), nullable=False),
        sa.Column('age_death_evidence', sa.JSON(), nullable=False),
        sa.Column('country_of_origin_evidence', sa.JSON(), nullable=False),
        sa.Column('race_ethnicity_evidence', sa.JSON(), nullable=False),
        sa.Column('affected_status_evidence', sa.JSON(), nullable=False),
        sa.Column('family_assignment_evidence', sa.JSON(), nullable=False),
        sa.Column('is_obligate_carrier_evidence', sa.JSON(), nullable=True),
        sa.Column('relationship_to_proband_evidence', sa.JSON(), nullable=True),
        sa.Column('twin_type_evidence', sa.JSON(), nullable=True),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['family_id'], ['families.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['agent_run_id'], ['agent_runs.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.create_index('ix_patients_paper_id', ['paper_id'], unique=False)
        batch_op.create_index('ix_patients_family_id', ['family_id'], unique=False)
        batch_op.create_index(
            'ix_patients_agent_run_id', ['agent_run_id'], unique=False
        )

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

    # Create variants table
    op.create_table(
        'variants',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('agent_run_id', sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ['agent_run_id'], ['agent_runs.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('variants', schema=None) as batch_op:
        batch_op.create_index('ix_variants_paper_id', ['paper_id'], unique=False)
        batch_op.create_index(
            'ix_variants_agent_run_id', ['agent_run_id'], unique=False
        )

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

    # Create patient_variant_occurrences table (formerly patient_variant_links)
    op.create_table(
        'patient_variant_occurrences',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('variant_id', sa.Integer(), nullable=False),
        sa.Column('paired_variant_link_id', sa.Integer(), nullable=True),
        sa.Column('zygosity', sa.String(), nullable=False),
        sa.Column('inheritance', sa.String(), nullable=False),
        sa.Column('de_novo', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column(
            'de_novo_evidence',
            sa.JSON(),
            nullable=False,
            server_default='{"value": false, "reasoning": "Not specified"}',
        ),
        sa.Column('disease_name', sa.String(), nullable=True),
        sa.Column('disease_name_evidence', sa.JSON(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ['paired_variant_link_id'],
            ['patient_variant_occurrences.id'],
            ondelete='SET NULL',
            name='fk_patient_variant_occurrences_paired',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'patient_id',
            'variant_id',
            name='uq_patient_variant_occurrences_patient_variant',
        ),
    )
    with op.batch_alter_table('patient_variant_occurrences', schema=None) as batch_op:
        batch_op.create_index(
            'ix_patient_variant_occurrences_patient_id', ['patient_id'], unique=False
        )
        batch_op.create_index(
            'ix_patient_variant_occurrences_variant_id', ['variant_id'], unique=False
        )
        batch_op.create_index(
            'ix_patient_variant_occurrences_paired_variant_link_id',
            ['paired_variant_link_id'],
            unique=False,
        )

    # Create annotated_variants table (formerly enriched_variants)
    op.create_table(
        'annotated_variants',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('variant_id', sa.Integer(), nullable=False),
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
            ['variant_id'],
            ['variants.id'],
            ondelete='CASCADE',
            name='fk_annotated_variants_variant_id_variants',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('variant_id', name='uq_annotated_variants_variant_id'),
    )
    with op.batch_alter_table('annotated_variants', schema=None) as batch_op:
        batch_op.create_index(
            'ix_annotated_variants_variant_id', ['variant_id'], unique=False
        )

    # Create hpos table
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

    # Create segregation_analysis_computed table
    op.create_table(
        'segregation_analysis_computed',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('family_id', sa.Integer(), nullable=False),
        sa.Column('segregation_count', sa.Integer(), nullable=False),
        sa.Column('segregation_count_reasoning', sa.JSON(), nullable=False),
        sa.Column('affected_count', sa.Integer(), nullable=False),
        sa.Column('affected_count_reasoning', sa.JSON(), nullable=False),
        sa.Column('unaffected_count', sa.Integer(), nullable=False),
        sa.Column('unaffected_count_reasoning', sa.JSON(), nullable=False),
        sa.Column('computed_lod_score', sa.Float(), nullable=False),
        sa.Column('computed_lod_score_reasoning', sa.JSON(), nullable=False),
        sa.Column('points_assigned', sa.Float(), nullable=False),
        sa.Column('points_assigned_reasoning', sa.JSON(), nullable=False),
        sa.Column('meets_minimum_criteria', sa.Boolean(), nullable=False),
        sa.Column('meets_minimum_criteria_reasoning', sa.JSON(), nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['family_id'], ['families.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('segregation_analysis_computed', schema=None) as batch_op:
        batch_op.create_index(
            'ix_segregation_analysis_computed_family_id', ['family_id'], unique=False
        )

    # Create segregation_evidence table
    op.create_table(
        'segregation_evidence',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('family_id', sa.Integer(), nullable=False),
        sa.Column('extracted_lod_score', sa.Float(), nullable=True),
        sa.Column('extracted_lod_score_evidence', sa.JSON(), nullable=True),
        sa.Column('has_unexplainable_non_segregations', sa.Boolean(), nullable=False),
        sa.Column(
            'has_unexplainable_non_segregations_evidence', sa.JSON(), nullable=False
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['family_id'], ['families.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('segregation_evidence', schema=None) as batch_op:
        batch_op.create_index(
            'ix_segregation_evidence_family_id', ['family_id'], unique=False
        )

    # Create conversations table
    op.create_table(
        'conversations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.String(), nullable=True),
        sa.Column('messages', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('paper_id'),
    )
    op.create_index(
        'ix_conversations_paper_id', 'conversations', ['paper_id'], unique=True
    )

    # Create tasks table
    op.create_table(
        'tasks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('agent_run_id', sa.Integer(), nullable=False),
        sa.Column(
            'type',
            sa.Enum(
                'PDF Parsing',
                'Paper Classifier',
                'General Paper Question',
                'Paper Metadata',
                'Variant Extraction',
                'Pedigree Description',
                'Patient Extraction',
                'Segregation Evidence Extraction',
                'Segregation Analysis Computed',
                'Variant Harmonization',
                'Variant Annotation',
                'Patient Variant Occurrences',
                'Phenotype Extraction',
                'HPO Linking',
                name='tasktype',
            ),
            nullable=False,
        ),
        sa.Column('family_id', sa.Integer(), nullable=True),
        sa.Column('patient_id', sa.Integer(), nullable=True),
        sa.Column('variant_id', sa.Integer(), nullable=True),
        sa.Column('phenotype_id', sa.Integer(), nullable=True),
        sa.Column(
            'status',
            sa.Enum(
                'Pending', 'Queued', 'Running', 'Completed', 'Failed', name='taskstatus'
            ),
            nullable=False,
        ),
        sa.Column('tries', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.String(), nullable=True),
        sa.Column('skip_successors', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('conversation_id', sa.String(), nullable=True),
        sa.Column('additional_context', sa.String(), nullable=True),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(['paper_id'], ['papers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['agent_run_id'], ['agent_runs.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(['family_id'], ['families.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['phenotype_id'], ['phenotypes.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_tasks_paper_id', 'tasks', ['paper_id'], unique=False)
    op.create_index('ix_tasks_agent_run_id', 'tasks', ['agent_run_id'], unique=False)
    op.create_index('ix_tasks_family_id', 'tasks', ['family_id'], unique=False)
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
        ['type', 'paper_id', 'family_id', 'patient_id', 'variant_id', 'phenotype_id'],
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
    op.drop_index('ix_tasks_family_id', table_name='tasks')
    op.drop_index('ix_tasks_agent_run_id', table_name='tasks')
    op.drop_index('ix_tasks_paper_id', table_name='tasks')
    op.drop_table('tasks')

    op.drop_index('ix_conversations_paper_id', table_name='conversations')
    op.drop_table('conversations')

    with op.batch_alter_table('segregation_evidence', schema=None) as batch_op:
        batch_op.drop_index('ix_segregation_evidence_family_id')
    op.drop_table('segregation_evidence')

    with op.batch_alter_table('segregation_analysis_computed', schema=None) as batch_op:
        batch_op.drop_index('ix_segregation_analysis_computed_family_id')
    op.drop_table('segregation_analysis_computed')

    op.drop_table('hpos')

    with op.batch_alter_table('annotated_variants', schema=None) as batch_op:
        batch_op.drop_index('ix_annotated_variants_variant_id')
    op.drop_table('annotated_variants')

    with op.batch_alter_table('patient_variant_occurrences', schema=None) as batch_op:
        batch_op.drop_index('ix_patient_variant_occurrences_paired_variant_link_id')
        batch_op.drop_index('ix_patient_variant_occurrences_variant_id')
        batch_op.drop_index('ix_patient_variant_occurrences_patient_id')
    op.drop_table('patient_variant_occurrences')

    with op.batch_alter_table('harmonized_variants', schema=None) as batch_op:
        batch_op.drop_index('ix_harmonized_variants_variant_id')
    op.drop_table('harmonized_variants')

    with op.batch_alter_table('phenotypes', schema=None) as batch_op:
        batch_op.drop_index('ix_phenotypes_patient_id')
        batch_op.drop_index('ix_phenotypes_paper_id')
    op.drop_table('phenotypes')

    with op.batch_alter_table('variants', schema=None) as batch_op:
        batch_op.drop_index('ix_variants_agent_run_id')
        batch_op.drop_index('ix_variants_paper_id')
    op.drop_table('variants')

    with op.batch_alter_table('pedigrees', schema=None) as batch_op:
        batch_op.drop_index('ix_pedigrees_paper_id')
    op.drop_table('pedigrees')

    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.drop_index('ix_patients_agent_run_id')
        batch_op.drop_index('ix_patients_family_id')
        batch_op.drop_index('ix_patients_paper_id')
    op.drop_table('patients')

    op.drop_index('ix_families_paper_id', table_name='families')
    op.drop_table('families')

    with op.batch_alter_table('papers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_papers_gene_id'))
        batch_op.drop_index(batch_op.f('ix_papers_content_hash'))
    op.drop_table('papers')

    op.drop_index('ix_agent_runs_updated_at', table_name='agent_runs')
    op.drop_index('ix_agent_runs_git_hash', table_name='agent_runs')
    op.drop_table('agent_runs')

    with op.batch_alter_table('genes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_genes_symbol'))
    op.drop_table('genes')
