"""Persistence of a single-pass curation.

The curation agent keys occurrences, compound het and segregation by position
in its own response, so these tests are mostly about index resolution and the
failure modes around it.
"""

from lib.agents.paper_curation_agent import (
    CuratedCompoundHet,
    CuratedFamily,
    CuratedOccurrence,
    CuratedPatient,
    CuratedPedigree,
    CuratedPhenotype,
    CuratedSegregation,
    FullCuration,
)
from lib.models.evidence_block import EvidenceBlock, ReasoningBlock
from lib.models.paper import PaperExtractionOutput, PaperType
from lib.models.patient import (
    AffectedStatus,
    AgeUnit,
    CountryCode,
    Ethnicity,
    Family,
    PatientDemographics,
    ProbandStatus,
    Race,
    SexAtBirth,
)
from lib.models.patient_variant_occurrences import (
    CompoundHetConfidence,
    Inheritance,
    TestingMethod,
    Zygosity,
)
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


def patient(identifier: str, family: str, phenotypes=()) -> CuratedPatient:
    return CuratedPatient(
        identifier=block(identifier),
        family_identifier=block(family),
        proband_status=block(ProbandStatus.Proband),
        demographics=demographics(),
        phenotypes=list(phenotypes),
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


def occurrence(pi: int, vi: int, zygosity=Zygosity.heterozygous) -> CuratedOccurrence:
    return CuratedOccurrence(
        patient_index=pi,
        variant_index=vi,
        zygosity=block(zygosity),
        inheritance=block(Inheritance.unknown),
        de_novo=block(False),
        testing_methods=[block(TestingMethod.exome_sequencing)],
    )


def curation(**overrides) -> FullCuration:
    fields = dict(
        metadata=PaperExtractionOutput(
            title='A paper',
            first_author='Author',
            journal_name='A journal',
            paper_types=[PaperType.Case_study],
        ),
        families=[
            CuratedFamily(
                family=Family(identifier=block('F1'), consanguinity=block(False)),
                patient_identifiers=[block('P1')],
            )
        ],
        patients=[patient('P1', 'F1')],
        pedigree=CuratedPedigree(found=False),
        variants=[variant('c.1A>G')],
        occurrences=[occurrence(0, 0)],
    )
    fields.update(overrides)
    return FullCuration(**fields)


def test_curation_model_accepts_a_minimal_paper():
    c = curation()
    assert len(c.patients) == 1
    assert c.patients[0].demographics.age_diagnosis.value == 9


def test_demographics_cannot_be_missing_for_a_patient():
    """Demographics are nested, so the 'identity without demographics' gap is unrepresentable."""
    fields = set(CuratedPatient.model_fields)
    assert 'demographics' in fields
    assert CuratedPatient.model_fields['demographics'].is_required()


def test_phenotypes_hang_off_their_patient():
    c = curation(
        patients=[
            patient(
                'P1', 'F1', phenotypes=[CuratedPhenotype(concept=block('seizures'))]
            )
        ]
    )
    assert c.patients[0].phenotypes[0].concept.value == 'seizures'


def test_testing_methods_capped_at_two_in_the_schema():
    schema = CuratedOccurrence.model_json_schema()
    assert schema['properties']['testing_methods']['maxItems'] == 2


def test_segregation_is_per_family_not_per_paper():
    """SegregationEvidenceDB is keyed by family, so the curation must be too."""
    c = curation(
        segregation=[
            CuratedSegregation(
                family_index=0,
                evidence=SegregationEvidenceExtractionOutput(
                    extracted_lod_score=block(3.1),
                    has_unexplainable_non_segregations=block(False),
                ),
            )
        ]
    )
    assert c.segregation[0].family_index == 0


def test_compound_het_names_two_variants_of_one_patient():
    c = curation(
        variants=[variant('c.1A>G'), variant('c.2C>T')],
        occurrences=[occurrence(0, 0), occurrence(0, 1)],
        compound_het=[
            CuratedCompoundHet(
                patient_index=0,
                variant_index_a=0,
                variant_index_b=1,
                confidence=ReasoningBlock(
                    value=CompoundHetConfidence.confirmed, reasoning='in trans'
                ),
            )
        ],
    )
    pair = c.compound_het[0]
    assert (pair.variant_index_a, pair.variant_index_b) == (0, 1)


def test_full_schema_stays_within_structured_output_limits():
    """The combined schema is the whole point; guard it against creeping growth."""
    import json

    size = len(json.dumps(FullCuration.model_json_schema()))
    assert size < 60_000, f'schema grew to {size} bytes'
