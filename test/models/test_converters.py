from lib.models import PaperDB, PaperExtractionOutput, PaperType
from lib.models.converters import (
    apply_patient_demographics,
    harmonized_variant_to_db,
    patient_identity_to_db,
)
from lib.models.evidence_block import EvidenceBlock, ReasoningBlock
from lib.models.patient import (
    AffectedStatus,
    AgeUnit,
    CountryCode,
    Ethnicity,
    PatientDemographics,
    PatientIdentity,
    ProbandStatus,
    Race,
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


def _identity(
    identifier: str = 'P1',
    family: str = 'Family1',
    proband: ProbandStatus = ProbandStatus.Proband,
) -> PatientIdentity:
    return PatientIdentity(
        identifier=EvidenceBlock(
            value=identifier, quote=f'referred to as {identifier}', reasoning='labeled'
        ),
        family_identifier=EvidenceBlock(
            value=family, quote=family, reasoning=f'belongs to {family}'
        ),
        proband_status=EvidenceBlock(
            value=proband, quote='index case', reasoning='stated'
        ),
    )


def test_patient_identity_to_db_sets_identity_and_placeholder_demographics():
    row = patient_identity_to_db('paper123', _identity(), agent_run_id=1)

    assert row.paper_id == 'paper123'
    assert row.agent_run_id == 1
    # Identity fields come from the agent
    assert row.identifier == 'P1'
    assert row.proband_status == 'Proband'
    assert row.identifier_evidence['value'] == 'P1'
    assert row.identifier_evidence['quote'] == 'referred to as P1'
    assert row.proband_status_evidence['value'] == 'Proband'

    # Demographics are placeholders until the demographics agent runs
    assert row.sex == 'Unknown'
    assert row.country_of_origin == 'Unknown'
    assert row.race == 'Unknown'
    assert row.ethnicity == 'Unknown'
    assert row.affected_status == 'Unknown'
    assert row.age_diagnosis is None
    assert row.age_diagnosis_unit is None
    assert row.age_report is None
    assert row.age_death is None
    assert row.is_obligate_carrier is False
    assert row.relationship_to_proband == 'Unknown'
    assert row.twin_type is None
    # Placeholder evidence blocks are populated (NOT NULL columns)
    assert row.sex_evidence['reasoning'] == 'Not yet extracted'
    assert row.race_evidence['value'] == 'Unknown'


def test_apply_patient_demographics_overwrites_placeholders():
    row = patient_identity_to_db('paper123', _identity(), agent_run_id=1)

    demographics = PatientDemographics(
        sex=EvidenceBlock(
            value=SexAtBirth.Female, quote='female patient', reasoning='stated female'
        ),
        age_diagnosis=EvidenceBlock(
            value=5, quote='diagnosed at 5', reasoning='age at diagnosis noted'
        ),
        age_diagnosis_unit=AgeUnit.Years,
        age_report=EvidenceBlock(
            value=10, quote='reported at 10', reasoning='age at report noted'
        ),
        age_report_unit=AgeUnit.Years,
        age_death=EvidenceBlock(
            value=None, image_id=1, reasoning='no death information available'
        ),
        country_of_origin=EvidenceBlock(
            value=CountryCode.Japan, quote='from Japan', reasoning='origin stated'
        ),
        race=EvidenceBlock(
            value=Race.Asian, quote='East Asian descent', reasoning='race stated'
        ),
        ethnicity=EvidenceBlock(
            value=Ethnicity.Not_Hispanic_or_Latino,
            quote='East Asian descent',
            reasoning='ethnicity stated',
        ),
        affected_status=EvidenceBlock(
            value=AffectedStatus.Affected,
            quote='affected individual',
            reasoning='clearly affected',
        ),
    )
    apply_patient_demographics(row, demographics)

    # Identity is untouched
    assert row.identifier == 'P1'
    assert row.proband_status == 'Proband'
    # Demographics now reflect the agent output
    assert row.sex == 'Female'
    assert row.age_diagnosis == 5
    assert row.age_diagnosis_unit == 'Years'
    assert row.age_report == 10
    assert row.age_report_unit == 'Years'
    assert row.age_death is None
    assert row.age_death_unit is None
    assert row.country_of_origin == 'Japan'
    assert row.race == 'Asian'
    assert row.ethnicity == 'Not Hispanic or Latino'
    assert row.affected_status == 'Affected'
    assert row.sex_evidence['value'] == 'Female'
    assert row.race_evidence['quote'] == 'East Asian descent'


def test_apply_patient_demographics_maps_segregation_analysis_fields():
    """Segregation analysis fields carried on demographics are applied."""
    row = patient_identity_to_db('paper_seg', _identity(), agent_run_id=1)

    demographics = PatientDemographics(
        sex=EvidenceBlock(value=SexAtBirth.Male, quote='male', reasoning='stated'),
        age_diagnosis=EvidenceBlock(value=None, table_id=1, reasoning='no age'),
        age_report=EvidenceBlock(value=None, table_id=1, reasoning='no age'),
        age_death=EvidenceBlock(value=None, table_id=1, reasoning='no death info'),
        country_of_origin=EvidenceBlock(
            value=CountryCode.Unknown, reasoning='not stated'
        ),
        race=EvidenceBlock(value=Race.Unknown, reasoning='not stated'),
        ethnicity=EvidenceBlock(value=Ethnicity.Unknown, reasoning='not stated'),
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
    apply_patient_demographics(row, demographics)

    assert row.is_obligate_carrier is True
    assert row.relationship_to_proband == 'Parent'
    assert row.twin_type == 'Monozygotic'
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
