"""Extraction verification: the flag-merge pass and its handler."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from lib.models import FamilyDB, FlagDB, GeneDB, PaperDB, PatientDB
from lib.models.flag import FlagMergeOutput
from lib.tasks.extraction_verification import (
    ALSO_RAISED,
    apply_merge,
    open_flags,
    verification_input,
)


@pytest.fixture
def paper(db_session):
    gene = GeneDB(symbol='TDO2')
    db_session.add(gene)
    db_session.flush()
    paper = PaperDB(content_hash='verify', gene_id=gene.id, filename='f.pdf')
    db_session.add(paper)
    db_session.flush()
    family = FamilyDB(
        paper_id=paper.id,
        identifier='Family A',
        identifier_evidence={'value': 'Family A', 'reasoning': 't'},
        consanguinity=False,
        consanguinity_evidence={'value': False, 'reasoning': 't'},
    )
    db_session.add(family)
    db_session.flush()
    patients = []
    for identifier in ('HYS272', 'HYS273'):
        p = PatientDB(
            paper_id=paper.id,
            family_id=family.id,
            identifier=identifier,
            identifier_evidence={'value': identifier, 'reasoning': 't'},
            proband_status='Unknown',
            proband_status_evidence={'value': 'Unknown', 'reasoning': 't'},
            sex='Unknown',
            sex_evidence={'value': 'Unknown', 'reasoning': 't'},
            age_diagnosis_evidence={'value': None, 'reasoning': 't'},
            age_report_evidence={'value': None, 'reasoning': 't'},
            age_death_evidence={'value': None, 'reasoning': 't'},
            country_of_origin='Unknown',
            country_of_origin_evidence={'value': 'Unknown', 'reasoning': 't'},
            race='Unknown',
            race_evidence={'value': 'Unknown', 'reasoning': 't'},
            ethnicity='Unknown',
            ethnicity_evidence={'value': 'Unknown', 'reasoning': 't'},
            affected_status='Unknown',
            affected_status_evidence={'value': 'Unknown', 'reasoning': 't'},
            family_assignment_evidence={'value': 'Family A', 'reasoning': 't'},
        )
        db_session.add(p)
        patients.append(p)
    db_session.flush()
    return paper, family, patients


def _flag(
    paper_id, subject, *, source='PATIENT_DEMOGRAPHICS', kind='inferred', **links
):
    return FlagDB(
        paper_id=paper_id,
        source=source,
        kind=kind,
        subject=subject,
        evidence={'value': subject, 'reasoning': f'because {subject}', 'citations': []},
        **links,
    )


@pytest.fixture
def taiwan(db_session, paper):
    """The paper 67 case: the same inference flagged for the father and the
    mother by separate demographics runs, plus one flag that stands alone."""
    paper_db, family, (father, mother) = paper
    rows = [
        _flag(
            paper_db.id,
            'Country of origin taken from recruitment site',
            patient_id=father.id,
        ),
        _flag(paper_db.id, 'Country of origin from study site', patient_id=mother.id),
        _flag(
            paper_db.id,
            'Younger sister label differs',
            kind='conflict',
            source='PATIENT_EXTRACTION',
        ),
    ]
    db_session.add_all(rows)
    db_session.flush()
    return rows


def _groups(*groups):
    return FlagMergeOutput(
        groups=[
            {'keep': g[0], 'merged': list(g[1:]), 'reasoning': 'same'} for g in groups
        ]
    )


def test_the_agent_sees_labels_not_ids(db_session, paper, taiwan):
    rows = verification_input(open_flags(db_session, paper[0].id))
    assert [r['about'] for r in rows] == ['patient HYS272', 'patient HYS273', None]
    assert rows[0]['agent'] == 'Patient Demographics'
    assert rows[2]['agent'] == 'Patient Extraction'
    assert (
        rows[0]['reasoning'] == 'because Country of origin taken from recruitment site'
    )
    assert set(rows[0]) == {'id', 'agent', 'kind', 'about', 'subject', 'reasoning'}


def test_a_decision_flagged_for_two_relatives_becomes_one_family_flag(
    db_session, paper, taiwan
):
    paper_db, family, (father, mother) = paper
    first, second, other = taiwan

    absorbed = apply_merge(db_session, paper_db.id, _groups((second.id, first.id)))

    assert absorbed == 1
    left = open_flags(db_session, paper_db.id)
    assert [f.id for f in left] == [first.id, other.id]
    # The earliest survives whatever the agent named as keep.
    survivor = left[0]
    assert survivor.patient_id is None
    assert survivor.family_id == family.id
    assert survivor.evidence['reasoning'] == (
        'because Country of origin taken from recruitment site\n\n'
        f'{ALSO_RAISED} Patient Demographics for patient HYS273: '
        'Country of origin from study site.'
    )
    # The rest of the evidence block is untouched.
    assert survivor.evidence['value'] == 'Country of origin taken from recruitment site'


def test_two_agents_flagging_the_same_patient_keep_the_patient(db_session, paper):
    paper_db, family, (father, _) = paper
    a = _flag(
        paper_db.id,
        'Pedigree label differs',
        kind='conflict',
        source='PATIENT_EXTRACTION',
        patient_id=father.id,
    )
    b = _flag(
        paper_db.id, 'Label differs from text', kind='conflict', patient_id=father.id
    )
    db_session.add_all([a, b])
    db_session.flush()

    apply_merge(db_session, paper_db.id, _groups((a.id, b.id)))

    (survivor,) = open_flags(db_session, paper_db.id)
    assert survivor.id == a.id
    assert survivor.patient_id == father.id
    assert survivor.family_id is None
    assert (
        f'{ALSO_RAISED} Patient Demographics for patient HYS272'
        in survivor.evidence['reasoning']
    )


def test_relatives_in_different_families_lift_to_the_paper(db_session, paper):
    paper_db, family, (father, mother) = paper
    other_family = FamilyDB(
        paper_id=paper_db.id,
        identifier='Family B',
        identifier_evidence={'value': 'Family B', 'reasoning': 't'},
        consanguinity=False,
        consanguinity_evidence={'value': False, 'reasoning': 't'},
    )
    db_session.add(other_family)
    db_session.flush()
    mother.family_id = other_family.id
    a = _flag(paper_db.id, 'Country from site', patient_id=father.id)
    b = _flag(paper_db.id, 'Country from site too', patient_id=mother.id)
    db_session.add_all([a, b])
    db_session.flush()

    apply_merge(db_session, paper_db.id, _groups((a.id, b.id)))

    (survivor,) = open_flags(db_session, paper_db.id)
    assert (survivor.patient_id, survivor.family_id) == (None, None)


def test_a_bad_group_is_skipped_and_the_rest_applied(db_session, paper, taiwan):
    paper_db, *_ = paper
    first, second, other = taiwan
    resolved = _flag(paper_db.id, 'settled already')
    resolved.resolved_at = datetime.now(timezone.utc)
    db_session.add(resolved)
    db_session.flush()

    absorbed = apply_merge(
        db_session,
        paper_db.id,
        _groups(
            (other.id, resolved.id),  # a resolved flag is not open: skipped
            (first.id, 999999),  # unknown id: skipped
            (first.id,),  # one flag is not a group: skipped
            (first.id, second.id),  # applied
            (second.id, other.id),  # second already used: skipped
        ),
    )

    assert absorbed == 1
    assert [f.id for f in open_flags(db_session, paper_db.id)] == [first.id, other.id]


def test_applying_the_same_answer_twice_changes_nothing_more(db_session, paper, taiwan):
    paper_db, *_ = paper
    first, second, other = taiwan
    answer = _groups((first.id, second.id))
    apply_merge(db_session, paper_db.id, answer)
    before = dict(open_flags(db_session, paper_db.id)[0].evidence)

    assert apply_merge(db_session, paper_db.id, answer) == 0
    assert open_flags(db_session, paper_db.id)[0].evidence == before


@pytest.fixture
def run_verification(monkeypatch, db_session, paper):
    """Drive handle_extraction_verification with a canned agent answer."""
    from lib.tasks import handlers
    from lib.tasks.models import TaskDB, TaskStatus, TaskType

    calls: list[str] = []

    async def run(output):
        async def fake_run(agent, message):
            calls.append(message)
            return SimpleNamespace(final_output=output, raw_responses=[])

        monkeypatch.setattr(handlers.Runner, 'run', fake_run)
        monkeypatch.setattr(handlers, 'log_run_metrics', lambda *a, **k: None)
        task = TaskDB(
            paper_id=paper[0].id,
            type=TaskType.EXTRACTION_VERIFICATION,
            status=TaskStatus.RUNNING,
        )
        db_session.add(task)
        db_session.commit()
        await handlers.handle_extraction_verification(task.id)
        db_session.expire_all()
        return calls

    return run


async def test_the_handler_merges_what_the_agent_groups(
    db_session, paper, taiwan, run_verification
):
    paper_db, family, _ = paper
    first, second, other = taiwan

    calls = await run_verification(_groups((first.id, second.id)))

    assert len(calls) == 1
    assert '"about": "patient HYS272"' in calls[0]
    assert 'Open flags on this paper' in calls[0]
    left = (
        db_session.query(FlagDB)
        .filter_by(paper_id=paper_db.id)
        .order_by(FlagDB.id)
        .all()
    )
    assert [(f.id, f.family_id) for f in left] == [
        (first.id, family.id),
        (other.id, None),
    ]


async def test_the_handler_asks_nothing_with_fewer_than_two_open_flags(
    db_session, paper, run_verification
):
    paper_db, *_ = paper
    db_session.add(_flag(paper_db.id, 'alone'))
    db_session.flush()

    calls = await run_verification(_groups())

    assert calls == []
    assert len(open_flags(db_session, paper_db.id)) == 1
