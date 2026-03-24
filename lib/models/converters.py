from lib.agents.pedigree_describer_agent import PedigreeExtractionOutput
from lib.models import ExtractedVariantDB, PatientDB, PedigreeDB
from lib.models.patient import Patient
from lib.models.variant import ExtractedVariant


def patient_to_db(paper_id: str, patient_idx: int, patient: Patient) -> PatientDB:
    """Convert a Patient to PatientDB, splitting values from evidence."""
    kwargs = {
        'paper_id': paper_id,
        'patient_idx': patient_idx,
    }

    # Extract values and evidence blocks for each field
    for field_name in Patient.model_fields:
        field_value = getattr(patient, field_name)
        kwargs[field_name] = field_value.value
        kwargs[f'{field_name}_evidence'] = field_value.model_dump()

    return PatientDB(**kwargs)


def pedigree_to_db(paper_id: str, pedigree: PedigreeExtractionOutput) -> PedigreeDB:
    """Convert PedigreeExtractionOutput to PedigreeDB."""
    return PedigreeDB(
        paper_id=paper_id,
        image_id=pedigree.image_id,
        description=pedigree.description,
    )


def variant_to_db(
    paper_id: str, variant_idx: int, variant: ExtractedVariant
) -> ExtractedVariantDB:
    """Convert Variant to ExtractedVariantDB, extracting values and evidence from EvidenceBlocks."""
    kwargs = {
        'paper_id': paper_id,
        'variant_idx': variant_idx,
        'gene': variant.gene,
    }

    # All fields except gene have evidence blocks
    evidence_fields = [
        'transcript',
        'protein_accession',
        'genomic_accession',
        'lrg_accession',
        'gene_accession',
        'genomic_coordinates',
        'genome_build',
        'rsid',
        'caid',
        'variant',
        'hgvs_c',
        'hgvs_p',
        'hgvs_g',
        'variant_type',
        'functional_evidence',
    ]

    for field_name in evidence_fields:
        evidence_block = getattr(variant, field_name)
        # Extract the value from the evidence block
        value = evidence_block.value
        # Handle enum types that need .value
        if field_name == 'genome_build' and value is not None:
            value = value.value
        elif field_name == 'variant_type':
            value = value.value
        kwargs[field_name] = value
        # Store the evidence block as dict
        kwargs[f'{field_name}_evidence'] = evidence_block.model_dump()

    return ExtractedVariantDB(**kwargs)
