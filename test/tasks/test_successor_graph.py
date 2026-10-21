"""Occurrences hangs off patient identity, and segregation waits for the last
demographics run.

Occurrences never reads what demographics fills in, so demographics is not
between patient extraction and occurrences any more: a one-patient
demographics re-run must not re-link the whole paper. What demographics does
feed is affected status, which both segregation steps read -- so segregation
evidence extraction is a fan-in of occurrences and every patient's
demographics, queued by whichever finishes second.
"""

import pytest

from lib.models import FamilyDB, GeneDB, HpoDB, PaperDB, PatientDB, PhenotypeDB
from lib.tasks.misc import enqueue_successors, invalidate_descendants
from lib.tasks.models import TASK_SUCCESSORS, TaskDB, TaskStatus, TaskType


@pytest.fixture
def paper(db_session):
    gene = GeneDB(symbol='CASP2')
    db_session.add(gene)
    db_session.flush()
    p = PaperDB(content_hash='graph123', gene_id=gene.id, filename='graph.pdf')
    db_session.add(p)
    db_session.flush()
    return p


def _task(db_session, paper, task_type, status=TaskStatus.COMPLETED, **kw):
    t = TaskDB(paper_id=paper.id, type=task_type, status=status, **kw)
    db_session.add(t)
    db_session.flush()
    return t


def _family(db_session, paper, identifier):
    f = FamilyDB(
        paper_id=paper.id,
        identifier=identifier,
        identifier_evidence=dict(value=identifier, reasoning='test'),
        consanguinity=False,
        consanguinity_evidence=dict(value=False, reasoning='test'),
    )
    db_session.add(f)
    db_session.flush()
    return f


def _patient(db_session, paper, family, identifier):
    unknown = dict(value='Unknown', reasoning='test')
    none = dict(value=None, reasoning='test')
    p = PatientDB(
        paper_id=paper.id,
        family_id=family.id,
        identifier=identifier,
        proband_status='Unknown',
        sex='Unknown',
        country_of_origin='Unknown',
        race='Unknown',
        ethnicity='Unknown',
        affected_status='Unknown',
        identifier_evidence=dict(value=identifier, reasoning='test'),
        family_assignment_evidence=dict(value=family.identifier, reasoning='test'),
        proband_status_evidence=unknown,
        sex_evidence=unknown,
        country_of_origin_evidence=unknown,
        race_evidence=unknown,
        ethnicity_evidence=unknown,
        affected_status_evidence=unknown,
        age_diagnosis_evidence=none,
        age_report_evidence=none,
        age_death_evidence=none,
    )
    db_session.add(p)
    db_session.flush()
    return p


def _queued(db_session, task_type):
    """(patient id, family id) of every PENDING row of that type."""
    return {
        (t.patient_id, t.family_id)
        for t in db_session.query(TaskDB).filter(
            TaskDB.type == task_type, TaskDB.status == TaskStatus.PENDING
        )
    }


def test_the_edges():
    assert TASK_SUCCESSORS[TaskType.PATIENT_EXTRACTION] == [
        TaskType.PATIENT_DEMOGRAPHICS,
        TaskType.PATIENT_VARIANT_OCCURRENCES,
    ]
    assert TASK_SUCCESSORS[TaskType.PATIENT_DEMOGRAPHICS] == [
        TaskType.PHENOTYPE_EXTRACTION,
        TaskType.SEGREGATION_EVIDENCE_EXTRACTION,
    ]
    assert (
        TaskType.SEGREGATION_EVIDENCE_EXTRACTION
        in (TASK_SUCCESSORS[TaskType.PATIENT_VARIANT_OCCURRENCES])
    )


def test_patient_extraction_queues_occurrences_once_variants_are_extracted(
    db_session, paper
):
    extraction = _task(db_session, paper, TaskType.PATIENT_EXTRACTION)
    enqueue_successors(db_session, extraction)
    assert _queued(db_session, TaskType.PATIENT_VARIANT_OCCURRENCES) == set()

    _task(db_session, paper, TaskType.VARIANT_EXTRACTION)
    enqueue_successors(db_session, extraction)
    assert _queued(db_session, TaskType.PATIENT_VARIANT_OCCURRENCES) == {(None, None)}


def test_variant_extraction_queues_occurrences_without_waiting_for_demographics(
    db_session, paper
):
    """The old gate held occurrences until every demographics run was in --
    an ordering trick, since occurrences reads none of it."""
    family = _family(db_session, paper, 'Family 1')
    p1 = _patient(db_session, paper, family, 'II-1')
    p2 = _patient(db_session, paper, family, 'II-2')
    _task(db_session, paper, TaskType.PATIENT_EXTRACTION)
    _task(
        db_session,
        paper,
        TaskType.PATIENT_DEMOGRAPHICS,
        TaskStatus.PENDING,
        patient_id=p1.id,
    )
    _task(
        db_session,
        paper,
        TaskType.PATIENT_DEMOGRAPHICS,
        TaskStatus.RUNNING,
        patient_id=p2.id,
    )

    enqueue_successors(
        db_session, _task(db_session, paper, TaskType.VARIANT_EXTRACTION)
    )

    assert _queued(db_session, TaskType.PATIENT_VARIANT_OCCURRENCES) == {(None, None)}


def test_segregation_waits_for_the_last_demographics(db_session, paper):
    """Segregation reads every patient's affected status, which demographics
    writes; occurrences finishing first queues nothing for it."""
    f1, f2 = (
        _family(db_session, paper, 'Family 1'),
        _family(db_session, paper, 'Family 2'),
    )
    p1, p2 = (
        _patient(db_session, paper, f1, 'II-1'),
        _patient(db_session, paper, f2, 'II-1'),
    )
    _task(db_session, paper, TaskType.PATIENT_EXTRACTION)
    _task(db_session, paper, TaskType.PATIENT_DEMOGRAPHICS, patient_id=p1.id)
    last = _task(
        db_session,
        paper,
        TaskType.PATIENT_DEMOGRAPHICS,
        TaskStatus.RUNNING,
        patient_id=p2.id,
    )

    enqueue_successors(
        db_session, _task(db_session, paper, TaskType.PATIENT_VARIANT_OCCURRENCES)
    )
    assert _queued(db_session, TaskType.SEGREGATION_EVIDENCE_EXTRACTION) == set()

    last.status = TaskStatus.COMPLETED
    enqueue_successors(db_session, last)
    assert _queued(db_session, TaskType.SEGREGATION_EVIDENCE_EXTRACTION) == {
        (None, f1.id),
        (None, f2.id),
    }
    assert _queued(db_session, TaskType.PHENOTYPE_EXTRACTION) == {(p2.id, None)}


def test_occurrences_queues_segregation_when_demographics_is_already_in(
    db_session, paper
):
    f1 = _family(db_session, paper, 'Family 1')
    p1 = _patient(db_session, paper, f1, 'II-1')
    _task(db_session, paper, TaskType.PATIENT_EXTRACTION)
    _task(db_session, paper, TaskType.PATIENT_DEMOGRAPHICS, patient_id=p1.id)

    enqueue_successors(
        db_session, _task(db_session, paper, TaskType.PATIENT_VARIANT_OCCURRENCES)
    )

    assert _queued(db_session, TaskType.SEGREGATION_EVIDENCE_EXTRACTION) == {
        (None, f1.id)
    }


def test_demographics_before_occurrences_queues_only_phenotypes(db_session, paper):
    f1 = _family(db_session, paper, 'Family 1')
    p1 = _patient(db_session, paper, f1, 'II-1')
    _task(db_session, paper, TaskType.PATIENT_EXTRACTION)
    demographics = _task(
        db_session, paper, TaskType.PATIENT_DEMOGRAPHICS, patient_id=p1.id
    )

    enqueue_successors(db_session, demographics)

    assert _queued(db_session, TaskType.PHENOTYPE_EXTRACTION) == {(p1.id, None)}
    assert _queued(db_session, TaskType.SEGREGATION_EVIDENCE_EXTRACTION) == set()
    assert _queued(db_session, TaskType.PATIENT_VARIANT_OCCURRENCES) == set()


def test_a_demographics_rerun_leaves_occurrences_and_their_branch_alone(
    db_session, paper
):
    """The point of the change: re-running demographics clears phenotypes,
    HPO, segregation and verification -- what reads its output -- and not
    the links, compound-het phasing or MONDO, which do not."""
    for task_type in (
        TaskType.PATIENT_VARIANT_OCCURRENCES,
        TaskType.COMPOUND_HET_EVALUATION,
        TaskType.PAPER_MONDO_LINKING,
        TaskType.OCCURRENCE_MONDO_LINKING,
        TaskType.PHENOTYPE_EXTRACTION,
        TaskType.HPO_LINKING,
        TaskType.SEGREGATION_EVIDENCE_EXTRACTION,
        TaskType.SEGREGATION_ANALYSIS_COMPUTED,
        TaskType.EXTRACTION_VERIFICATION,
    ):
        _task(db_session, paper, task_type)

    invalidate_descendants(db_session, paper.id, TaskType.PATIENT_DEMOGRAPHICS)

    remaining = {t.type for t in db_session.query(TaskDB).all()}
    assert remaining == {
        TaskType.PATIENT_VARIANT_OCCURRENCES,
        TaskType.COMPOUND_HET_EVALUATION,
        TaskType.PAPER_MONDO_LINKING,
        TaskType.OCCURRENCE_MONDO_LINKING,
    }


def test_demographics_skips_phenotypes_for_an_unaffected_patient(db_session, paper):
    """An unaffected relative's features are not evidence for the gene, so
    the pipeline does not extract them; Unknown still counts as affected."""
    f1 = _family(db_session, paper, 'Family 1')
    unaffected = _patient(db_session, paper, f1, 'I-1')
    unaffected.affected_status = 'Unaffected'
    unknown = _patient(db_session, paper, f1, 'II-1')
    db_session.flush()

    for patient in (unaffected, unknown):
        enqueue_successors(
            db_session,
            _task(
                db_session, paper, TaskType.PATIENT_DEMOGRAPHICS, patient_id=patient.id
            ),
        )

    assert _queued(db_session, TaskType.PHENOTYPE_EXTRACTION) == {(unknown.id, None)}


def test_phenotype_extraction_queues_hpo_for_every_unlinked_phenotype(
    db_session, paper
):
    """Whatever the patient's variants: linking used to wait for a variant
    occurrence, which left a manual phenotype run linking nothing. A
    phenotype the extraction linked from the cache needs no task."""
    f1 = _family(db_session, paper, 'Family 1')
    p1 = _patient(db_session, paper, f1, 'II-1')  # no occurrence
    evidence = {'value': 'x', 'reasoning': 't', 'citations': []}
    unlinked = PhenotypeDB(
        paper_id=paper.id,
        patient_id=p1.id,
        concept='Seizures',
        concept_evidence=evidence,
    )
    cached = PhenotypeDB(
        paper_id=paper.id, patient_id=p1.id, concept='Ataxia', concept_evidence=evidence
    )
    cached.hpo = HpoDB(hpo_id='HP:0001251', hpo_name='Ataxia', reasoning='cached')
    db_session.add_all([unlinked, cached])
    db_session.flush()

    enqueue_successors(
        db_session,
        _task(db_session, paper, TaskType.PHENOTYPE_EXTRACTION, patient_id=p1.id),
    )

    queued = db_session.query(TaskDB).filter(
        TaskDB.type == TaskType.HPO_LINKING, TaskDB.status == TaskStatus.PENDING
    )
    assert {t.phenotype_id for t in queued} == {unlinked.id}
