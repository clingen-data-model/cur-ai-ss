"""Persisting what each reading pass returned.

Splitting the passes into separate tasks means every entity a later pass refers
to is a database row by the time it runs, so the passes are handed real ids and
hand them back. What is left to get wrong is an id we never supplied -- a model
can still return one -- and the binding between a patient and its phenotypes.
"""

import pytest

from lib.agents.paper_extraction import (
    CompoundHetForPatient,
    FamilySegregation,
    Genotypes,
    PaperStructure,
    PatientDetail,
    PatientDetails,
    SegregationFindings,
    variant_label,
)
from lib.models import FamilyDB, GeneDB, PaperDB, PatientDB, VariantDB
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
    PatientVariantOccurrenceDB,
    TestingMethod,
    Zygosity,
)
from lib.models.phenotype import ExtractedPhenotype, PhenotypeDB
from lib.models.segregation_analysis import (
    SegregationEvidenceDB,
    SegregationEvidenceExtractionOutput,
)
from lib.models.variant import Variant, VariantType
from lib.tasks.paper_extraction import (
    persist_details,
    persist_genotypes,
    persist_pedigree,
    persist_segregation,
    persist_structure,
)


def block(value):
    return EvidenceBlock(value=value, reasoning='r', quote='q')


@pytest.fixture
def paper(db_session):
    gene = GeneDB(symbol='CAD')
    db_session.add(gene)
    db_session.flush()
    row = PaperDB(id=89, gene_id=gene.id, filename='p.pdf', content_hash='h')
    db_session.add(row)
    db_session.flush()
    return row


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


def structure(patients: list[str], families: list[str], variants: list[str]):
    return PaperStructure(
        classification=PaperClassification(
            paper_types=[PaperType.Case_study],
            is_paper_relevant=ReasoningBlock(value=True, reasoning='has cases'),
        ),
        patients=PatientExtractionOutput(
            patients=[identity(name, families[0]) for name in patients],
            families=[
                FamilyEntry(
                    family=Family(identifier=block(f), consanguinity=block(False)),
                    patient_identifiers=[block(p) for p in patients],
                )
                for f in families
            ],
        ),
        variants=[variant(v) for v in variants],
    )


def seed(session, run, paper_id=89):
    """The state the later passes are handed: one family, two patients, one variant."""
    stored = persist_structure(
        session,
        paper_id,
        run.id,
        structure(['III-1', 'III-2'], ['Family 1'], ['c.1A>G']),
    )
    session.flush()
    patients = session.query(PatientDB).order_by(PatientDB.id).all()
    variants = session.query(VariantDB).order_by(VariantDB.id).all()
    return stored, patients, variants


def test_structure_writes_the_entities_later_passes_are_keyed_to(
    db_session, agent_run, paper
):
    stored, patients, variants = seed(db_session, agent_run)
    assert stored == {'families': 1, 'patients': 2, 'variants': 1}
    assert [p.identifier for p in patients] == ['III-1', 'III-2']
    assert db_session.get(PaperDB, 89).is_paper_relevant is True


def test_a_patient_naming_an_unlisted_family_still_lands(db_session, agent_run, paper):
    """patients.family_id is NOT NULL, so the family is created rather than the
    patient being dropped."""
    s = structure(['III-1'], ['Family 1'], [])
    s.patients.patients[0].family_identifier = block('Family 9')

    stored = persist_structure(db_session, 89, agent_run.id, s)

    assert stored['patients'] == 1
    assert stored['families'] == 2
    patient = db_session.query(PatientDB).one()
    assert db_session.get(FamilyDB, patient.family_id).identifier == 'Family 9'


def test_rerunning_structure_replaces_what_the_other_passes_produced(
    db_session, agent_run, paper
):
    """The later passes were keyed to entities this pass replaces, so their
    output cannot outlive it."""
    _, patients, variants = seed(db_session, agent_run)
    persist_details(
        db_session,
        89,
        PatientDetails(
            patients=[
                PatientDetail(
                    patient_id=patients[0].id,
                    demographics=demographics(),
                    phenotypes=[phenotype(patients[0].id, 'seizures')],
                )
            ]
        ),
    )
    db_session.flush()
    assert db_session.query(PhenotypeDB).count() == 1

    persist_structure(
        db_session, 89, agent_run.id, structure(['III-1'], ['Family 1'], [])
    )
    db_session.flush()

    assert db_session.query(PhenotypeDB).count() == 0
    assert db_session.query(PatientDB).count() == 1


def test_details_bind_phenotypes_by_nesting(db_session, agent_run, paper):
    """A phenotype's own patient_id disagreeing with the patient it was
    returned under would otherwise be silent, so the nesting decides."""
    _, patients, _ = seed(db_session, agent_run)
    stored = persist_details(
        db_session,
        89,
        PatientDetails(
            patients=[
                PatientDetail(
                    patient_id=patients[1].id,
                    demographics=demographics(),
                    phenotypes=[
                        # patient_id disagrees with the nesting on purpose
                        phenotype(patients[0].id, 'seizures')
                    ],
                )
            ]
        ),
    )
    db_session.flush()

    assert stored == {'described': 1, 'phenotypes': 1}
    assert db_session.query(PhenotypeDB).one().patient_id == patients[1].id
    assert db_session.get(PatientDB, patients[1].id).age_diagnosis == 9


def test_details_for_a_patient_we_never_sent_are_dropped(db_session, agent_run, paper):
    _, patients, _ = seed(db_session, agent_run)
    stored = persist_details(
        db_session,
        89,
        PatientDetails(
            patients=[
                PatientDetail(patient_id=999_999, demographics=demographics()),
                PatientDetail(patient_id=patients[0].id, demographics=demographics()),
            ]
        ),
    )
    assert stored['described'] == 1


def test_genotypes_link_real_rows_and_pair_compound_hets(db_session, agent_run, paper):
    persist_structure(
        db_session,
        89,
        agent_run.id,
        structure(['III-1'], ['Family 1'], ['c.1A>G', 'c.2C>T']),
    )
    db_session.flush()
    patient = db_session.query(PatientDB).one()
    variants = db_session.query(VariantDB).order_by(VariantDB.id).all()

    stored = persist_genotypes(
        db_session,
        89,
        Genotypes(
            occurrences=[
                occurrence(patient.id, variants[0].id),
                occurrence(patient.id, variants[1].id),
            ],
            compound_het=[
                CompoundHetForPatient(
                    patient_id=patient.id,
                    pairs=[
                        CompoundHetPair(
                            variant_id_a=variants[0].id,
                            variant_id_b=variants[1].id,
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
    db_session.flush()

    assert stored == {'occurrences': 2, 'compound_het_pairs': 1}
    rows = (
        db_session.query(PatientVariantOccurrenceDB)
        .order_by(PatientVariantOccurrenceDB.id)
        .all()
    )
    # The pairing points both ways, so either row shows the other.
    assert rows[0].paired_variant_link_id == rows[1].id
    assert rows[1].paired_variant_link_id == rows[0].id


def test_genotypes_naming_an_id_we_never_sent_are_dropped(db_session, agent_run, paper):
    _, patients, variants = seed(db_session, agent_run)
    stored = persist_genotypes(
        db_session,
        89,
        Genotypes(
            occurrences=[
                occurrence(patients[0].id, 999_999),
                occurrence(999_999, variants[0].id),
                occurrence(patients[0].id, variants[0].id),
            ]
        ),
    )
    assert stored['occurrences'] == 1


def test_segregation_is_stored_against_the_family_it_names(
    db_session, agent_run, paper
):
    seed(db_session, agent_run)
    family = db_session.query(FamilyDB).one()

    stored = persist_segregation(
        db_session,
        89,
        SegregationFindings(
            families=[
                FamilySegregation(family_id=family.id, evidence=evidence(3.1)),
                FamilySegregation(family_id=999_999, evidence=evidence(9.9)),
            ]
        ),
    )
    db_session.flush()

    assert stored == {'segregation_families': 1}
    row = db_session.query(SegregationEvidenceDB).one()
    assert row.family_id == family.id
    assert row.extracted_lod_score == 3.1


def test_pedigree_is_replaced_not_appended(db_session, agent_run, paper):
    found = PedigreeExtractionOutput(found=True, image_id=2, description='II-1 male')
    assert persist_pedigree(db_session, 89, found) == {'pedigrees': 1}
    db_session.flush()
    assert persist_pedigree(db_session, 89, found) == {'pedigrees': 1}
    db_session.flush()

    assert persist_pedigree(db_session, 89, PedigreeExtractionOutput(found=False)) == {
        'pedigrees': 0
    }


def test_variant_label_names_a_row_the_model_can_find_in_the_paper(
    db_session, agent_run, paper
):
    _, _, variants = seed(db_session, agent_run)
    assert variant_label(variants[0]) == 'c.1A>G'

    variants[0].hgvs_c = None
    variants[0].variant = None
    assert variant_label(variants[0]) == 'unnamed variant'


def test_testing_methods_capped_at_two_in_the_schema():
    """A Pydantic validator would be invisible to structured outputs; maxItems
    is not."""
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


def test_every_pass_is_bounded_in_time():
    """A run once sat blocked on one pass for 2h47m with the socket still open.

    Each pass is its own task now, so the bound it has to fit is that task's
    lease rather than the whole chain's.
    """
    from lib.agents.paper_extraction import _shared
    from lib.bin.worker import lease_timeout_for
    from lib.tasks.models import TaskType

    worst_case = _shared._ATTEMPT_TIMEOUT_S * (_shared._MAX_RETRIES + 1)
    for task_type in (
        TaskType.PEDIGREE_IDENTIFICATION,
        TaskType.PAPER_STRUCTURE,
        TaskType.PATIENT_DETAILS,
        TaskType.PATIENT_GENOTYPES,
        TaskType.SEGREGATION_EVIDENCE,
    ):
        assert worst_case < lease_timeout_for(task_type)


def occurrence(patient_id: int, variant_id: int) -> PatientVariantOccurrence:
    return PatientVariantOccurrence(
        patient_id=patient_id,
        variant_id=variant_id,
        zygosity=block(Zygosity.heterozygous),
        inheritance=block(Inheritance.unknown),
        de_novo=block(False),
        testing_methods=[block(TestingMethod.exome_sequencing)],
    )


def phenotype(patient_id: int, concept: str) -> ExtractedPhenotype:
    return ExtractedPhenotype(
        patient_id=patient_id,
        concept=block(concept),
        onset=None,
        location=None,
        severity=None,
        modifier=None,
    )


def evidence(lod: float) -> SegregationEvidenceExtractionOutput:
    return SegregationEvidenceExtractionOutput(
        extracted_lod_score=block(lod),
        has_unexplainable_non_segregations=block(False),
    )
