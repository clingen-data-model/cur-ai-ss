from lib.models import PaperDB, PaperExtractionOutput, PaperType
from lib.models.converters import harmonized_variant_to_db, patient_to_db
from lib.models.evidence_block import EvidenceBlock, ReasoningBlock
from lib.models.patient import (
    AffectedStatus,
    AgeUnit,
    CountryCode,
    Patient,
    ProbandStatus,
    RaceEthnicity,
    RelationshipToProband,
    SexAtBirth,
    TwinType,
)
from lib.models.variant import HarmonizedVariant


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
    assert paper_db.paper_types == ['Research', 'Case Study']


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
        age_diagnosis_unit=AgeUnit.Years,
        age_report=EvidenceBlock(
            value=10, quote='reported at 10', reasoning='age at report noted'
        ),
        age_report_unit=AgeUnit.Years,
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
    row = patient_to_db('paper123', patient)

    assert row.paper_id == 'paper123'
    # Values
    assert row.identifier == 'P1'
    assert row.proband_status == 'Proband'
    assert row.sex == 'Female'
    assert row.age_diagnosis == 5
    assert row.age_diagnosis_unit == 'Years'
    assert row.age_report == 10
    assert row.age_report_unit == 'Years'
    assert row.age_death is None
    assert row.age_death_unit is None
    assert row.country_of_origin == 'Japan'
    assert row.race_ethnicity == 'East Asian'
    assert row.affected_status == 'Affected'
    # Segregation analysis fields (defaults)
    assert row.is_obligate_carrier is False
    assert row.relationship_to_proband == 'Unknown'
    assert row.twin_type is None
    # Evidence blocks
    assert row.identifier_evidence['value'] == 'P1'
    assert row.identifier_evidence['quote'] == 'referred to as P1'
    assert row.identifier_evidence['reasoning'] == 'labeled P1 in table'
    # Segregation evidence blocks (defaults)
    assert row.is_obligate_carrier_evidence is not None
    assert row.relationship_to_proband_evidence is not None
    assert row.twin_type_evidence is not None


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
    row = patient_to_db('paper456', patient)

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
    # Segregation analysis fields (defaults)
    assert row.is_obligate_carrier is False
    assert row.relationship_to_proband == 'Unknown'
    assert row.twin_type is None


def test_patient_to_db_maps_segregation_analysis_fields():
    """Test that segregation analysis fields are correctly converted."""
    patient = Patient(
        identifier=EvidenceBlock(value='P1', quote='patient 1', reasoning='labeled P1'),
        proband_status=EvidenceBlock(
            value=ProbandStatus.Proband, quote='index', reasoning='proband'
        ),
        sex=EvidenceBlock(value=SexAtBirth.Male, quote='male', reasoning='stated'),
        age_diagnosis=EvidenceBlock(value=10, quote='age 10', reasoning='at diagnosis'),
        age_diagnosis_unit=AgeUnit.Years,
        age_report=EvidenceBlock(value=None, table_id=1, reasoning='no age'),
        age_death=EvidenceBlock(value=None, table_id=1, reasoning='no death info'),
        country_of_origin=EvidenceBlock(
            value=CountryCode.Unknown, quote='unknown', reasoning='not stated'
        ),
        race_ethnicity=EvidenceBlock(
            value=RaceEthnicity.Unknown, quote='unknown', reasoning='not stated'
        ),
        affected_status=EvidenceBlock(
            value=AffectedStatus.Affected, quote='affected', reasoning='disease'
        ),
        is_obligate_carrier=EvidenceBlock(
            value=True,
            quote='mother of affected child',
            reasoning='pedigree position indicates carrier',
        ),
        relationship_to_proband=EvidenceBlock(
            value=RelationshipToProband.Parent,
            quote='father',
            reasoning='stated as parent',
        ),
        twin_type=EvidenceBlock(
            value=TwinType.Monozygotic,
            quote='identical twins',
            reasoning='explicitly stated',
        ),
    )
    row = patient_to_db('paper_seg', patient)

    # Segregation fields should be set correctly
    assert row.is_obligate_carrier is True
    assert row.relationship_to_proband == 'Parent'
    assert row.twin_type == 'Monozygotic'

    # Evidence blocks should be serialized
    assert row.is_obligate_carrier_evidence['value'] is True
    assert row.is_obligate_carrier_evidence['quote'] == 'mother of affected child'
    assert row.relationship_to_proband_evidence['value'] == 'Parent'
    assert row.twin_type_evidence['value'] == 'Monozygotic'


def test_harmonized_variant_to_db_with_all_fields():
    """Test converting HarmonizedVariant with all fields populated."""
    harmonized_data = HarmonizedVariant(
        gnomad_style_coordinates='1-55051215-G-A',
        rsid='rs80356779',
        caid='CA123456',
        hgvs_c='NM_007294.3:c.4675G>A',
        hgvs_p='NP_007295.3:p.Arg1559Lys',
        hgvs_g='NC_000017.11:g.41197819G>A',
    )
    reasoning_block = ReasoningBlock(
        value=harmonized_data,
        reasoning='Successfully normalized via VariantValidator and allele registry lookup.',
    )

    result = harmonized_variant_to_db(42, reasoning_block)

    assert result.variant_id == 42
    assert result.gnomad_style_coordinates == '1-55051215-G-A'
    assert result.rsid == 'rs80356779'
    assert result.caid == 'CA123456'
    assert result.hgvs_c == 'NM_007294.3:c.4675G>A'
    assert result.hgvs_p == 'NP_007295.3:p.Arg1559Lys'
    assert result.hgvs_g == 'NC_000017.11:g.41197819G>A'
    assert (
        result.reasoning
        == 'Successfully normalized via VariantValidator and allele registry lookup.'
    )


def test_harmonized_variant_to_db_with_none_value():
    """Test converting HarmonizedVariant with None value."""
    reasoning_block = ReasoningBlock(
        value=None,
        reasoning='Could not normalize variant: insufficient data',
    )

    result = harmonized_variant_to_db(99, reasoning_block)

    assert result.variant_id == 99
    assert result.gnomad_style_coordinates is None
    assert result.rsid is None
    assert result.caid is None
    assert result.hgvs_c is None
    assert result.hgvs_p is None
    assert result.hgvs_g is None
    assert result.reasoning == 'Could not normalize variant: insufficient data'


def test_harmonized_variant_to_db_with_partial_fields():
    """Test converting HarmonizedVariant with only some fields populated."""
    harmonized_data = HarmonizedVariant(
        gnomad_style_coordinates='12-25389391-C-T',
        rsid='rs1003702',
        caid=None,  # Explicitly None
        hgvs_c='NM_001267550.1:c.7271C>T',
        hgvs_p=None,  # Missing
        hgvs_g=None,
    )
    reasoning_block = ReasoningBlock(
        value=harmonized_data,
        reasoning='Normalized via transcript-based projection.',
    )

    result = harmonized_variant_to_db(5, reasoning_block)

    assert result.variant_id == 5
    assert result.gnomad_style_coordinates == '12-25389391-C-T'
    assert result.rsid == 'rs1003702'
    assert result.caid is None
    assert result.hgvs_c == 'NM_001267550.1:c.7271C>T'
    assert result.hgvs_p is None
    assert result.hgvs_g is None
    assert result.reasoning == 'Normalized via transcript-based projection.'
