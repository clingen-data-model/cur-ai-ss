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


def test_terminal_task_types_are_the_pipelines_leaves(client):
    body = client.get('/stats').json()

    assert set(body['terminal_task_types']) == {
        TaskType.VARIANT_ANNOTATION.value,
        TaskType.SEGREGATION_ANALYSIS_COMPUTED.value,
        TaskType.HPO_LINKING.value,
        TaskType.MONDO_LINKING.value,
        TaskType.COMPOUND_HET_EVALUATION.value,
    }


def test_predecessor_task_types_is_the_reverse_of_the_dag(client):
    """A fan-out type's rows are safe to treat as final once every direct
    predecessor instance is Completed -- this is the mapping that check reads."""
    body = client.get('/stats').json()
    predecessors = body['predecessor_task_types']

    assert predecessors[TaskType.HPO_LINKING.value] == [
        TaskType.PHENOTYPE_EXTRACTION.value
    ]
    assert set(predecessors[TaskType.PATIENT_VARIANT_OCCURRENCES.value]) == {
        TaskType.PATIENT_DEMOGRAPHICS.value,
        TaskType.VARIANT_EXTRACTION.value,
    }
    assert set(predecessors[TaskType.MONDO_LINKING.value]) == {
        TaskType.PAPER_METADATA.value,
        TaskType.PATIENT_VARIANT_OCCURRENCES.value,
    }
    # The pipeline's root has no predecessor.
    assert predecessors.get(TaskType.PDF_PARSING.value, []) == []
