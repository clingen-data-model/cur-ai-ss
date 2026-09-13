"""Historical task durations, as the progress estimates consume them."""

import datetime

import pytest

from lib.models import GeneDB, PaperDB, TaskDB
from lib.tasks.models import TaskStatus, TaskType

BASE = datetime.datetime(2026, 9, 13, 12, 0, 0, tzinfo=datetime.timezone.utc)


@pytest.fixture
def paper(db_session):
    gene = GeneDB(symbol='BRCA1')
    db_session.add(gene)
    db_session.flush()
    row = PaperDB(gene_id=gene.id, filename='p.pdf', content_hash='h')
    db_session.add(row)
    db_session.flush()
    return row


@pytest.fixture
def add_task(db_session, paper):
    def _add(seconds, status=TaskStatus.COMPLETED, type=TaskType.PDF_PARSING):
        started = BASE if seconds is not None else None
        db_session.add(
            TaskDB(
                paper_id=paper.id,
                type=type,
                status=status,
                started_at=started,
                updated_at=(
                    BASE + datetime.timedelta(seconds=seconds)
                    if seconds is not None
                    else BASE
                ),
            )
        )
        db_session.flush()

    return _add


def _by_type(body):
    return {d['type']: d for d in body['task_durations']}


def test_reports_median_and_p90_per_type(client, add_task):
    for s in [10, 20, 30, 40, 1000]:
        add_task(s)

    body = client.get('/stats').json()

    stat = _by_type(body)['PDF Parsing']
    assert stat['samples'] == 5
    # Median, not mean: the 1000s outlier moves a mean to 220 and leaves the
    # median at 30, which is the point of choosing it.
    assert stat['median_seconds'] == 30
    assert stat['p90_seconds'] == 1000


def test_running_tasks_are_excluded(client, add_task):
    """A RUNNING task has started_at == updated_at, so counting it would
    contribute a zero and drag every median toward nothing."""
    add_task(60)
    add_task(0, status=TaskStatus.RUNNING)

    stat = _by_type(client.get('/stats').json())['PDF Parsing']

    assert stat['samples'] == 1
    assert stat['median_seconds'] == 60


def test_pending_tasks_are_excluded(client, add_task):
    add_task(60)
    add_task(None, status=TaskStatus.PENDING)

    assert _by_type(client.get('/stats').json())['PDF Parsing']['samples'] == 1


def test_failed_runs_are_counted(client, add_task):
    """They consumed real time; dropping them biases the numbers toward
    whatever happened to succeed."""
    add_task(10)
    add_task(90, status=TaskStatus.FAILED)

    stat = _by_type(client.get('/stats').json())['PDF Parsing']

    assert stat['samples'] == 2
    # Nearest-rank, so p50 of [10, 90] is the lower of the two rather than
    # their average -- every reported figure is a duration something actually
    # took, never an interpolation between two that never happened.
    assert stat['median_seconds'] == 10


def test_types_are_reported_separately(client, add_task):
    add_task(10, type=TaskType.PDF_PARSING)
    add_task(600, type=TaskType.HPO_LINKING)

    stats = _by_type(client.get('/stats').json())

    assert stats['PDF Parsing']['median_seconds'] == 10
    assert stats['HPO Linking']['median_seconds'] == 600


def test_overall_median_backs_types_with_no_history(client, add_task):
    """A newly added agent has no samples; treating it as free would make a
    progress bar finish and then stall."""
    for s in [10, 20, 30]:
        add_task(s)

    body = client.get('/stats').json()

    assert body['overall_median_seconds'] == 20
    assert body['total_samples'] == 3


def test_empty_database_reports_no_history(client):
    body = client.get('/stats').json()

    assert body['task_durations'] == []
    assert body['overall_median_seconds'] is None
    assert body['total_samples'] == 0


def _track(body, track_id):
    return next(t for t in body['tracks'] if t['id'] == track_id)


def test_tracks_measure_wall_clock_not_the_sum_of_tasks(client, add_task, db_session):
    """Tasks inside a track overlap, so summing their durations would overstate
    the track badly. Two 60s tasks starting together span 60s, not 120s."""
    for _ in range(2):
        add_task(60, type=TaskType.PDF_PARSING)

    track = _track(client.get('/stats').json(), 'paper')

    assert track['median_seconds'] == 60
    assert track['papers'] == 1


def test_a_tracks_span_covers_its_whole_membership(client, add_task, paper, db_session):
    """Pedigree and HPO Linking are both Patients, so the track runs from the
    first start to the last finish across all of them."""
    import datetime

    db_session.add(
        TaskDB(
            paper_id=paper.id,
            type=TaskType.PEDIGREE_DESCRIPTION,
            status=TaskStatus.COMPLETED,
            started_at=BASE,
            updated_at=BASE + datetime.timedelta(seconds=30),
        )
    )
    db_session.add(
        TaskDB(
            paper_id=paper.id,
            type=TaskType.HPO_LINKING,
            status=TaskStatus.COMPLETED,
            started_at=BASE + datetime.timedelta(seconds=100),
            updated_at=BASE + datetime.timedelta(seconds=250),
        )
    )
    db_session.flush()

    assert _track(client.get('/stats').json(), 'patients')['median_seconds'] == 250


def test_every_track_is_reported_even_without_history(client):
    """The bars read their grouping from here, so a track with no measurements
    still has to appear -- with null durations rather than being absent."""
    body = client.get('/stats').json()

    assert [t['id'] for t in body['tracks']] == [
        'paper',
        'patients',
        'variants',
        'analysis',
    ]
    for track in body['tracks']:
        assert track['median_seconds'] is None
        assert track['papers'] == 0
        assert track['task_types']


def test_track_membership_covers_every_pipeline_type_but_chat(client):
    """Guards the grouping the frontend no longer keeps its own copy of."""
    from lib.tasks.models import TaskType as T

    body = client.get('/stats').json()
    assigned = [t for track in body['tracks'] for t in track['task_types']]

    assert len(assigned) == len(set(assigned)), 'a type is in two tracks'
    assert set(assigned) == {t.value for t in T} - {T.GENERAL_PAPER_QUESTION.value}
