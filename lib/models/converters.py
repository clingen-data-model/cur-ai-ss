from lib.agents.pedigree_describer_agent import PedigreeExtractionOutput
from lib.agents.variant_extraction_agent import Variant
from lib.models import ExtractedVariantDB, PatientDB, PedigreeDB
from lib.models.patient import Patient


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


def variant_to_db(paper_id: str, variant_idx: int, variant: Variant) -> ExtractedVariantDB:
    """Convert Variant to ExtractedVariantDB."""
    return ExtractedVariantDB(
        paper_id=paper_id,
        variant_idx=variant_idx,
        **variant.model_dump(),
    )
