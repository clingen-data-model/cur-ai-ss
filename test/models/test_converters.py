from lib.agents.patient_extraction_agent import (
    AffectedStatus,
    CountryCode,
    PatientInfo,
    ProbandStatus,
    RaceEthnicity,
    SexAtBirth,
)
from lib.models import PaperDB, PaperExtractionOutput, PaperType
from lib.models.converters import patient_info_to_db


def test_apply_to_maps_all_fields():
    output = PaperExtractionOutput(
        title='A Novel Variant in BRCA1',
        first_author='Smith',
        journal_name='Nature Genetics',
        abstract='We describe a novel variant...',
        publication_year=2024,
        doi='10.1234/ng.5678',
        pmid='12345678',
        pmcid='PMC9999999',
        paper_types=[PaperType.Research, PaperType.Case_study],
    )
    paper_db = PaperDB(id='test-id', gene_id='1', filename='test.pdf')
    output.apply_to(paper_db)

    assert paper_db.title == 'A Novel Variant in BRCA1'
    assert paper_db.first_author == 'Smith'
    assert paper_db.journal_name == 'Nature Genetics'
    assert paper_db.abstract == 'We describe a novel variant...'
    assert paper_db.publication_year == 2024
    assert paper_db.doi == '10.1234/ng.5678'
    assert paper_db.pmid == '12345678'
    assert paper_db.pmcid == 'PMC9999999'
    assert paper_db.paper_types == ['Research', 'Case_study']


def test_apply_to_handles_none_fields():
    output = PaperExtractionOutput(
        title='Minimal Paper',
        first_author='Doe',
        journal_name=None,
        paper_types=[PaperType.Unknown],
    )
    paper_db = PaperDB(id='test-id-2', gene_id='1', filename='test2.pdf')
    output.apply_to(paper_db)

    assert paper_db.title == 'Minimal Paper'
    assert paper_db.first_author == 'Doe'
    assert paper_db.journal_name is None
    assert paper_db.abstract is None
    assert paper_db.publication_year is None
    assert paper_db.doi is None
    assert paper_db.pmid is None
    assert paper_db.pmcid is None
    assert paper_db.paper_types == ['Unknown']


def test_patient_info_to_db_maps_all_fields():
    patient = PatientInfo(
        identifier='P1',
        proband_status=ProbandStatus.Proband,
        sex=SexAtBirth.Female,
        age_diagnosis='5 years',
        age_report='10 years',
        age_death=None,
        country_of_origin=CountryCode.Japan,
        race_ethnicity=RaceEthnicity.East_Asian,
        affected_status=AffectedStatus.Affected,
        identifier_evidence_context='referred to as P1',
        proband_status_evidence_context='index case',
        sex_evidence_context='female patient',
        age_diagnosis_evidence_context='diagnosed at 5',
        age_report_evidence_context='reported at 10',
        age_death_evidence_context=None,
        country_of_origin_evidence_context='from Japan',
        race_ethnicity_evidence_context='East Asian descent',
        affected_status_evidence_context='affected individual',
        identifier_reasoning='labeled P1 in table',
        proband_status_reasoning='first identified',
        sex_reasoning='stated female',
        age_diagnosis_reasoning='age at diagnosis noted',
        age_report_reasoning='age at report noted',
        age_death_reasoning=None,
        country_of_origin_reasoning='origin stated',
        race_ethnicity_reasoning='ethnicity stated',
        affected_status_reasoning='clearly affected',
    )
    row = patient_info_to_db('paper123', 1, patient)

    assert row.paper_id == 'paper123'
    assert row.patient_idx == 1
    assert row.identifier == 'P1'
    # Enum fields stored as plain strings
    assert row.proband_status == 'Proband'
    assert row.sex == 'Female'
    assert row.country_of_origin == 'Japan'
    assert row.race_ethnicity == 'East Asian'
    assert row.affected_status == 'Affected'
    # Age fields
    assert row.age_diagnosis == '5 years'
    assert row.age_report == '10 years'
    assert row.age_death is None
    # Evidence fields
    assert row.identifier_evidence_context == 'referred to as P1'
    assert row.proband_status_evidence_context == 'index case'
    assert row.sex_evidence_context == 'female patient'
    assert row.age_death_evidence_context is None
    # Reasoning direct mapping
    assert row.identifier_reasoning == 'labeled P1 in table'
    assert row.affected_status_reasoning == 'clearly affected'


def test_patient_info_to_db_handles_optional_none_fields():
    patient = PatientInfo(
        identifier='II-2',
        proband_status=ProbandStatus.Unknown,
        sex=SexAtBirth.Unknown,
        age_diagnosis=None,
        age_report=None,
        age_death=None,
        country_of_origin=CountryCode.Unknown,
        race_ethnicity=RaceEthnicity.Unknown,
        affected_status=AffectedStatus.Unknown,
        identifier_evidence_context=None,
        proband_status_evidence_context=None,
        sex_evidence_context=None,
        age_diagnosis_evidence_context=None,
        age_report_evidence_context=None,
        age_death_evidence_context=None,
        country_of_origin_evidence_context=None,
        race_ethnicity_evidence_context=None,
        affected_status_evidence_context=None,
        identifier_reasoning=None,
        proband_status_reasoning=None,
        sex_reasoning=None,
        age_diagnosis_reasoning=None,
        age_report_reasoning=None,
        age_death_reasoning=None,
        country_of_origin_reasoning=None,
        race_ethnicity_reasoning=None,
        affected_status_reasoning=None,
    )
    row = patient_info_to_db('paper456', 3, patient)

    assert row.identifier == 'II-2'
    assert row.proband_status == 'Unknown'
    assert row.sex == 'Unknown'
    assert row.country_of_origin == 'Unknown'
    assert row.race_ethnicity == 'Unknown'
    assert row.affected_status == 'Unknown'
    assert row.age_diagnosis is None
    assert row.age_report is None
    assert row.age_death is None
    assert row.identifier_evidence_context is None
    assert row.identifier_reasoning is None
