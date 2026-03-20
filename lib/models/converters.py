from lib.models import PatientDB
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
