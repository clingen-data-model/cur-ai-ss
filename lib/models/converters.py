from lib.agents.patient_extraction_agent import PatientInfo
from lib.models import PatientDB


def patient_info_to_db(
    paper_id: str, position: int, patient_info: PatientInfo
) -> PatientDB:
    """Convert a PatientInfo agent output to a PatientDB row."""
    return PatientDB(
        paper_id=paper_id,
        position=position,
        **patient_info.model_dump(mode='json'),
    )
