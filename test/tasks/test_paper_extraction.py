"""Persistence of a single-pass curation.

The curation agent keys occurrences, compound het and segregation by position
in its own response, so these tests are mostly about index resolution and the
failure modes around it.
"""

from lib.agents.one_shot_paper_extraction_agent import (
    OneShotFamily,
    OneShotPaperExtraction,
    OneShotPatient,
)
from lib.models.evidence_block import EvidenceBlock, ReasoningBlock
from lib.models.paper import (
    PaperClassification,
    PaperType,
    PedigreeExtractionOutput,
)
from lib.models.patient import (
    AffectedStatus,
    AgeUnit,
    CountryCode,
    Ethnicity,
    Family,
    FamilyEntry,
    PatientDemographics,
    ProbandStatus,
    Race,
    SexAtBirth,
)
from lib.models.patient_variant_occurrences import (
    CompoundHetConfidence,
    CompoundHetPair,
    Inheritance,
    PatientVariantOccurrence,
    TestingMethod,
    Zygosity,
)
from lib.models.phenotype import ExtractedPhenotype
from lib.models.segregation_analysis import SegregationEvidenceExtractionOutput
from lib.models.variant import Variant, VariantType


def block(value):
    return EvidenceBlock(value=value, reasoning='r', quote='q')


def demographics(**overrides) -> PatientDemographics:
    fields = dict(
        sex=block(SexAtBirth.Male),
        age_diagnosis=block(9),
        age_diagnosis_unit=AgeUnit.Years,
        age_report=block(None),
        age_death=block(None),
        country_of_origin=block(CountryCode.Unknown),
        race=block(Race.Unknown),
        ethnicity=block(Ethnicity.Unknown),
        affected_status=block(AffectedStatus.Affected),
    )
    fields.update(overrides)
    return PatientDemographics(**fields)


def patient(identifier: str, family: str) -> OneShotPatient:
    """PatientIdentity fields plus the demographics for that patient."""
    return OneShotPatient(
        identifier=block(identifier),
        family_identifier=block(family),
        proband_status=block(ProbandStatus.Proband),
        demographics=demographics(),
    )


def variant(hgvs: str) -> Variant:
    empty = block(None)
    return Variant(
        variant=block(hgvs),
        transcript=empty,
        protein_accession=empty,
        genomic_accession=empty,
        lrg_accession=empty,
        gene_accession=empty,
        genomic_coordinates=empty,
        genome_build=empty,
        rsid=empty,
        caid=empty,
        hgvs_c=block(hgvs),
        hgvs_p=empty,
        hgvs_g=empty,
        variant_type=block(VariantType.missense),
        functional_evidence=block(False),
        main_focus=block(True),
    )


def occurrence(pi: int, vi: int, zygosity=Zygosity.heterozygous):
    """patient_id/variant_id carry INDICES here, not database ids."""
    return PatientVariantOccurrence(
        patient_id=pi,
        variant_id=vi,
        zygosity=block(zygosity),
        inheritance=block(Inheritance.unknown),
        de_novo=block(False),
        testing_methods=[block(TestingMethod.exome_sequencing)],
    )


def curation(**overrides) -> OneShotPaperExtraction:
    fields = dict(
        classification=PaperClassification(paper_types=[PaperType.Case_study]),
        families=[
            OneShotFamily(
                family=Family(identifier=block('F1'), consanguinity=block(False)),
                patient_identifiers=[block('P1')],
            )
        ],
        patients=[patient('P1', 'F1')],
        pedigree=PedigreeExtractionOutput(found=False),
        variants=[variant('c.1A>G')],
        occurrences=[occurrence(0, 0)],
    )
    fields.update(overrides)
    return OneShotPaperExtraction(**fields)


def test_curation_model_accepts_a_minimal_paper():
    c = curation()
    assert len(c.patients) == 1
    assert c.patients[0].demographics.age_diagnosis.value == 9


def test_patient_is_identity_plus_demographics():
    """OneShotPatient reuses PatientIdentity and adds the demographics to it."""
    from lib.models.patient import PatientIdentity

    assert issubclass(OneShotPatient, PatientIdentity)
    assert set(PatientIdentity.model_fields) <= set(OneShotPatient.model_fields)
    # nesting is what makes 'identified but undescribed' unrepresentable
    assert OneShotPatient.model_fields['demographics'].is_required()


def test_phenotypes_reuse_the_existing_model_keyed_by_index():
    c = curation(
        phenotypes=[
            ExtractedPhenotype(
                patient_id=0,
                concept=block('seizures'),
                onset=None,
                location=None,
                severity=None,
                modifier=None,
            )
        ]
    )
    # patient_id is a position in curation.patients, not a database id
    assert c.phenotypes[0].patient_id == 0
    assert c.phenotypes[0].concept.value == 'seizures'


def test_testing_methods_capped_at_two_in_the_schema():
    schema = PatientVariantOccurrence.model_json_schema()
    assert schema['properties']['testing_methods']['maxItems'] == 2


def test_segregation_hangs_off_its_family():
    """SegregationEvidenceDB is keyed by family, so the evidence nests there."""
    c = curation(
        families=[
            OneShotFamily(
                family=Family(identifier=block('F1'), consanguinity=block(False)),
                patient_identifiers=[block('P1')],
                segregation=SegregationEvidenceExtractionOutput(
                    extracted_lod_score=block(3.1),
                    has_unexplainable_non_segregations=block(False),
                ),
            )
        ]
    )
    assert c.families[0].segregation.extracted_lod_score.value == 3.1
    # and a family without segregation evidence is fine
    assert curation().families[0].segregation is None


def test_compound_het_hangs_off_its_patient():
    carrier = patient('P1', 'F1')
    carrier.compound_het = [
        CompoundHetPair(
            variant_id_a=0,
            variant_id_b=1,
            confidence=ReasoningBlock(
                value=CompoundHetConfidence.confirmed, reasoning='in trans'
            ),
        )
    ]
    c = curation(
        patients=[carrier],
        variants=[variant('c.1A>G'), variant('c.2C>T')],
        occurrences=[occurrence(0, 0), occurrence(0, 1)],
    )
    pair = c.patients[0].compound_het[0]
    # variant ids are indices into curation.variants here
    assert (pair.variant_id_a, pair.variant_id_b) == (0, 1)


def test_full_schema_stays_within_structured_output_limits():
    """The combined schema is the whole point; guard it against creeping growth."""
    import json

    size = len(json.dumps(OneShotPaperExtraction.model_json_schema()))
    assert size < 60_000, f'schema grew to {size} bytes'
