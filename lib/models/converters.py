from lib.agents.patient_extraction_agent import PatientInfo
from lib.models import PatientDB


def patient_info_to_db(
    paper_id: str, position: int, patient_info: PatientInfo
) -> PatientDB:
    """Convert a PatientInfo agent output to a PatientDB row."""
    return PatientDB(
        paper_id=paper_id,
        position=position,
        identifier=patient_info.identifier,
        proband_status=patient_info.proband_status.value,
        sex=patient_info.sex.value,
        age_diagnosis=patient_info.age_diagnosis,
        age_report=patient_info.age_report,
        age_death=patient_info.age_death,
        country_of_origin=patient_info.country_of_origin.value,
        race_ethnicity=patient_info.race_ethnicity.value,
        affected_status=patient_info.affected_status.value,
        # Evidence fields
        identifier_evidence_context=patient_info.identifier_evidence_context,
        proband_status_evidence_context=patient_info.proband_status_evidence_context,
        sex_evidence_context=patient_info.sex_evidence_context,
        age_diagnosis_evidence_context=patient_info.age_diagnosis_evidence_context,
        age_report_evidence_context=patient_info.age_report_evidence_context,
        age_death_evidence_context=patient_info.age_death_evidence_context,
        country_of_origin_evidence_context=patient_info.country_of_origin_evidence_context,
        race_ethnicity_evidence_context=patient_info.race_ethnicity_evidence_context,
        affected_status_evidence_context=patient_info.affected_status_evidence_context,
        # Reasoning fields (direct mapping)
        identifier_reasoning=patient_info.identifier_reasoning,
        proband_status_reasoning=patient_info.proband_status_reasoning,
        sex_reasoning=patient_info.sex_reasoning,
        age_diagnosis_reasoning=patient_info.age_diagnosis_reasoning,
        age_report_reasoning=patient_info.age_report_reasoning,
        age_death_reasoning=patient_info.age_death_reasoning,
        country_of_origin_reasoning=patient_info.country_of_origin_reasoning,
        race_ethnicity_reasoning=patient_info.race_ethnicity_reasoning,
        affected_status_reasoning=patient_info.affected_status_reasoning,
    )
