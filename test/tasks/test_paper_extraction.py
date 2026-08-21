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


# --- superseded task cleanup -------------------------------------------------


def _task(session, agent_run, paper_id: int, task_type, **kw):
    from lib.tasks.models import TaskDB, TaskStatus

    row = TaskDB(
        paper_id=paper_id,
        type=task_type,
        status=kw.pop('status', TaskStatus.COMPLETED),
        agent_run_id=agent_run.id,
        **kw,
    )
    session.add(row)
    session.flush()
    return row


def test_superseded_tasks_cleared_only_for_the_re_extracted_paper(
    db_session, agent_run
):
    """Other papers keep their history; this one loses rows nothing will run again."""
    from lib.models import GeneDB, PaperDB
    from lib.tasks.models import TaskDB, TaskType
    from lib.tasks.paper_extraction import clear_superseded_tasks

    gene = GeneDB(symbol='BRCA1')
    db_session.add(gene)
    db_session.flush()
    for pid in (1, 2):
        db_session.add(
            PaperDB(
                id=pid,
                filename=f'p{pid}.pdf',
                content_hash=f'hash{pid}',
                gene_id=gene.id,
            )
        )
    db_session.flush()

    # the paper being re-extracted
    _task(db_session, agent_run, 1, TaskType.PATIENT_EXTRACTION)
    _task(db_session, agent_run, 1, TaskType.PAPER_METADATA)
    _task(db_session, agent_run, 1, TaskType.PDF_PARSING)
    _task(db_session, agent_run, 1, TaskType.HPO_LINKING)
    _task(db_session, agent_run, 1, TaskType.PAPER_EXTRACTION)
    # a different paper, still on the old pipeline
    _task(db_session, agent_run, 2, TaskType.PATIENT_EXTRACTION)

    removed = clear_superseded_tasks(db_session, paper_id=1)

    assert removed == 2
    remaining = {
        t.type for t in db_session.query(TaskDB).filter(TaskDB.paper_id == 1).all()
    }
    # still-scheduled types survive, including the task doing the work
    assert remaining == {
        TaskType.PDF_PARSING,
        TaskType.HPO_LINKING,
        TaskType.PAPER_EXTRACTION,
    }
    # the other paper is untouched
    assert db_session.query(TaskDB).filter(TaskDB.paper_id == 2).count() == 1


def test_paper_extraction_never_deletes_itself():
    from lib.tasks.models import SUPERSEDED_BY_PAPER_EXTRACTION, TaskType

    assert TaskType.PAPER_EXTRACTION not in SUPERSEDED_BY_PAPER_EXTRACTION


def test_superseded_set_matches_what_the_graph_no_longer_reaches():
    """Every type unreachable from PDF_PARSING should be one we clean up."""
    from lib.tasks.models import (
        SUPERSEDED_BY_PAPER_EXTRACTION,
        TASK_SUCCESSORS,
        TaskType,
    )

    reachable, frontier = set(), [TaskType.PDF_PARSING]
    while frontier:
        t = frontier.pop()
        if t in reachable:
            continue
        reachable.add(t)
        frontier.extend(TASK_SUCCESSORS.get(t, []))

    # GENERAL_PAPER_QUESTION is a chat pseudo-task, never scheduled by the worker
    orphaned = {
        t
        for t in TaskType
        if t not in reachable and t != TaskType.GENERAL_PAPER_QUESTION
    }
    assert orphaned == SUPERSEDED_BY_PAPER_EXTRACTION
