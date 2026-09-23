"""The pipeline's structure, as GET /stats reports it for live progress."""

from lib.tasks.models import TaskType


def test_every_track_is_reported(client):
    body = client.get('/stats').json()

    assert [t['id'] for t in body['tracks']] == [
        'paper',
        'patients',
        'variants',
        'analysis',
    ]
    for track in body['tracks']:
        assert track['label']
        assert track['task_types']
        assert isinstance(track['stage'], int)


def test_track_membership_covers_every_pipeline_type(client):
    """Guards the grouping the frontend no longer keeps its own copy of."""
    body = client.get('/stats').json()
    assigned = [t for track in body['tracks'] for t in track['task_types']]

    assert len(assigned) == len(set(assigned)), 'a type is in two tracks'
    assert set(assigned) == {t.value for t in TaskType}
