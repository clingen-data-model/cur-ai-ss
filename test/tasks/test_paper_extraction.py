"""The extraction passes and how their results resolve to database rows.

Each pass names patients, variants and families differently -- pass 2 by
identifier, passes 3 and 4 by position in a list they were handed -- because
none of them exist in the database yet. Getting that wrong attaches a phenotype
to the wrong patient silently, so it is what these tests are about.
"""

from lib.agents.paper_extraction import PaperExtraction, _variant_label
from lib.agents.paper_extraction.details import PatientDetail, PatientDetails
from lib.agents.paper_extraction.genotypes import CompoundHetForPatient, Genotypes
from lib.agents.paper_extraction.segregation import (
    FamilySegregation,
    SegregationFindings,
)
from lib.models.evidence_block import EvidenceBlock, ReasoningBlock
from lib.models.paper import PaperClassification, PaperType, PedigreeExtractionOutput
from lib.models.patient import (
    AffectedStatus,
    AgeUnit,
    CountryCode,
    Ethnicity,
    Family,
    FamilyEntry,
    PatientDemographics,
    PatientExtractionOutput,
    PatientIdentity,
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


def identity(name: str, family: str) -> PatientIdentity:
    return PatientIdentity(
        identifier=block(name),
        family_identifier=block(family),
        proband_status=block(ProbandStatus.Proband),
    )


def family_entry(name: str, members: list[str]) -> FamilyEntry:
    return FamilyEntry(
        family=Family(identifier=block(name), consanguinity=block(False)),
        patient_identifiers=[block(m) for m in members],
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


def occurrence(patient_index: int, variant_index: int) -> PatientVariantOccurrence:
    """patient_id/variant_id carry POSITIONS here, not database ids."""
    return PatientVariantOccurrence(
        patient_id=patient_index,
        variant_id=variant_index,
        zygosity=block(Zygosity.heterozygous),
        inheritance=block(Inheritance.unknown),
        de_novo=block(False),
        testing_methods=[block(TestingMethod.exome_sequencing)],
    )


def extraction(**overrides) -> PaperExtraction:
    fields = dict(
        classification=PaperClassification(
            paper_types=[PaperType.Case_study],
            is_paper_relevant=ReasoningBlock(value=True, reasoning='has cases'),
        ),
        pedigree=PedigreeExtractionOutput(found=False),
        patients=PatientExtractionOutput(
            patients=[identity('P1', 'F1')],
            families=[family_entry('F1', ['P1'])],
        ),
        details=PatientDetails(
            patients=[PatientDetail(identifier='P1', demographics=demographics())]
        ),
        variants=[variant('c.1A>G')],
        genotypes=Genotypes(occurrences=[occurrence(0, 0)]),
        segregation=SegregationFindings(),
    )
    fields.update(overrides)
    return PaperExtraction(**fields)


def test_extraction_assembles_from_the_passes():
    e = extraction()
    assert e.patients.patients[0].identifier.value == 'P1'
    assert e.details.patients[0].demographics.age_diagnosis.value == 9


def test_pass_two_keys_by_identifier_not_position():
    """Pass 2 is handed names, so a reordered response still lands correctly."""
    e = extraction(
        patients=PatientExtractionOutput(
            patients=[identity('P1', 'F1'), identity('P2', 'F1')],
            families=[family_entry('F1', ['P1', 'P2'])],
        ),
        details=PatientDetails(
            patients=[
                PatientDetail(identifier='P2', demographics=demographics()),
                PatientDetail(identifier='P1', demographics=demographics()),
            ]
        ),
    )
    assert [d.identifier for d in e.details.patients] == ['P2', 'P1']


def test_phenotypes_are_nested_under_their_patient():
    """Nesting is what persistence trusts; the patient_id field is not consulted."""
    detail = PatientDetail(
        identifier='P1',
        demographics=demographics(),
        phenotypes=[
            ExtractedPhenotype(
                patient_id=0,
                concept=block('seizures'),
                onset=None,
                location=None,
                severity=None,
                modifier=None,
            )
        ],
    )
    e = extraction(details=PatientDetails(patients=[detail]))
    assert e.details.patients[0].phenotypes[0].concept.value == 'seizures'


def test_compound_het_names_a_patient_and_two_variants():
    e = extraction(
        variants=[variant('c.1A>G'), variant('c.2C>T')],
        genotypes=Genotypes(
            occurrences=[occurrence(0, 0), occurrence(0, 1)],
            compound_het=[
                CompoundHetForPatient(
                    patient_index=0,
                    pairs=[
                        CompoundHetPair(
                            variant_id_a=0,
                            variant_id_b=1,
                            confidence=ReasoningBlock(
                                value=CompoundHetConfidence.confirmed,
                                reasoning='in trans',
                            ),
                        )
                    ],
                )
            ],
        ),
    )
    pair = e.genotypes.compound_het[0].pairs[0]
    assert (pair.variant_id_a, pair.variant_id_b) == (0, 1)


def test_segregation_is_keyed_by_family_position():
    """SegregationEvidenceDB is keyed by family, so the pass is too."""
    e = extraction(
        segregation=SegregationFindings(
            families=[
                FamilySegregation(
                    family_index=0,
                    evidence=SegregationEvidenceExtractionOutput(
                        extracted_lod_score=block(3.1),
                        has_unexplainable_non_segregations=block(False),
                    ),
                )
            ]
        )
    )
    assert e.segregation.families[0].evidence.extracted_lod_score.value == 3.1


def test_variant_label_prefers_the_most_identifying_form():
    """Later passes see variants by name, so the name has to identify them."""
    v = variant('c.1A>G')
    assert _variant_label(v) == 'c.1A>G'

    empty = block(None)
    unnamed = v.model_copy(update={'hgvs_c': empty, 'variant': empty})
    assert _variant_label(unnamed) == 'unnamed variant'


def test_testing_methods_capped_at_two_in_the_schema():
    schema = PatientVariantOccurrence.model_json_schema()
    assert schema['properties']['testing_methods']['maxItems'] == 2


def test_no_pass_embeds_the_shared_evidence_contract():
    """_run appends it, so a prompt embedding it too would send it twice."""
    from lib.agents.core_extraction_rules import CORE_EXTRACTION_SPEC
    from lib.agents.paper_extraction.details import DETAIL_INSTRUCTIONS
    from lib.agents.paper_extraction.genotypes import GENOTYPE_INSTRUCTIONS
    from lib.agents.paper_extraction.pedigree import PEDIGREE_INSTRUCTIONS
    from lib.agents.paper_extraction.segregation import SEGREGATION_INSTRUCTIONS
    from lib.agents.paper_extraction.structure import STRUCTURE_INSTRUCTIONS

    for prompt in (
        PEDIGREE_INSTRUCTIONS,
        STRUCTURE_INSTRUCTIONS,
        DETAIL_INSTRUCTIONS,
        GENOTYPE_INSTRUCTIONS,
        SEGREGATION_INSTRUCTIONS,
    ):
        assert CORE_EXTRACTION_SPEC not in prompt
        assert len(prompt) > 200


def test_the_split_does_not_change_the_pipeline_graph():
    """Passes live inside one task, so successors are unaffected."""
    from lib.tasks.models import TASK_SUCCESSORS, TaskType
    from lib.ui.paper.tasks import PIPELINE_ORDER

    for task, successors in TASK_SUCCESSORS.items():
        for successor in successors:
            assert PIPELINE_ORDER[task] < PIPELINE_ORDER[successor]

    assert TaskType.PAPER_EXTRACTION in TASK_SUCCESSORS
