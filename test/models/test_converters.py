from lib.models import PaperDB, PaperExtractionOutput, PaperType
from lib.models.converters import patient_to_db
from lib.models.evidence_block import EvidenceBlock
from lib.models.patient import (
    AffectedStatus,
    CountryCode,
    Patient,
    ProbandStatus,
    RaceEthnicity,
    SexAtBirth,
)


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


def test_patient_to_db_maps_all_fields():
    patient = Patient(
        identifier=EvidenceBlock(
            value='P1',
            quote='referred to as P1',
            reasoning='labeled P1 in table',
        ),
        proband_status=EvidenceBlock(
            value=ProbandStatus.Proband,
            quote='index case',
            reasoning='first identified',
        ),
        sex=EvidenceBlock(
            value=SexAtBirth.Female,
            quote='female patient',
            reasoning='stated female',
        ),
        age_diagnosis=EvidenceBlock(
            value=5,
            quote='diagnosed at 5',
            reasoning='age at diagnosis noted',
        ),
        age_report=EvidenceBlock(
            value=10, quote='reported at 10', reasoning='age at report noted'
        ),
        age_death=EvidenceBlock(
            value=None,
            quote=None,
            image_id=1,
            reasoning='no death information available',
        ),
        country_of_origin=EvidenceBlock(
            value=CountryCode.Japan,
            quote='from Japan',
            reasoning='origin stated',
        ),
        race_ethnicity=EvidenceBlock(
            value=RaceEthnicity.East_Asian,
            quote='East Asian descent',
            reasoning='ethnicity stated',
        ),
        affected_status=EvidenceBlock(
            value=AffectedStatus.Affected,
            quote='affected individual',
            reasoning='clearly affected',
        ),
    )
    row = patient_to_db('paper123', 1, patient)

    assert row.paper_id == 'paper123'
    assert row.patient_idx == 1
    # Values
    assert row.identifier == 'P1'
    assert row.proband_status == 'Proband'
    assert row.sex == 'Female'
    assert row.age_diagnosis == 5
    assert row.age_report == 10
    assert row.age_death is None
    assert row.country_of_origin == 'Japan'
    assert row.race_ethnicity == 'East Asian'
    assert row.affected_status == 'Affected'
    # Evidence blocks
    assert row.identifier_evidence['value'] == 'P1'
    assert row.identifier_evidence['quote'] == 'referred to as P1'
    assert row.identifier_evidence['reasoning'] == 'labeled P1 in table'


def test_patient_to_db_handles_optional_none_values():
    patient = Patient(
        identifier=EvidenceBlock(
            value='II-2',
            quote='pedigree notation',
            reasoning='labeled in pedigree',
        ),
        proband_status=EvidenceBlock(
            value=ProbandStatus.Unknown,
            quote=None,
            image_id=1,
            reasoning='unclear from pedigree',
        ),
        sex=EvidenceBlock(
            value=SexAtBirth.Unknown, table_id=2, reasoning='not specified'
        ),
        age_diagnosis=EvidenceBlock(
            value=None, table_id=2, reasoning='no diagnosis age provided'
        ),
        age_report=EvidenceBlock(
            value=None,
            quote=None,
            table_id=2,
            reasoning='no report age available',
        ),
        age_death=EvidenceBlock(
            value=None, table_id=2, reasoning='no death information'
        ),
        country_of_origin=EvidenceBlock(
            value=CountryCode.Unknown,
            quote='location not stated',
            reasoning='no origin information',
        ),
        race_ethnicity=EvidenceBlock(
            value=RaceEthnicity.Unknown,
            quote=None,
            image_id=1,
            reasoning='ethnicity not mentioned',
        ),
        affected_status=EvidenceBlock(
            value=AffectedStatus.Unknown,
            quote='status unclear',
            reasoning='phenotype not detailed',
        ),
    )
    row = patient_to_db('paper456', 3, patient)

    assert row.identifier == 'II-2'
    assert row.proband_status == 'Unknown'
    assert row.sex == 'Unknown'
    assert row.country_of_origin == 'Unknown'
    assert row.race_ethnicity == 'Unknown'
    assert row.affected_status == 'Unknown'
    assert row.age_diagnosis is None
    assert row.age_report is None
    assert row.age_death is None
    # Evidence always present
    assert row.identifier_evidence is not None
    assert row.proband_status_evidence is not None
