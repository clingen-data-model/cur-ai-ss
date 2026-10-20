from lib.tasks.models import TASK_SUCCESSORS, TaskType


def test_every_task_type_is_listed_with_a_description(client):
    response = client.get('/task-types')

    assert response.status_code == 200
    assert [row['type'] for row in response.json()] == [t.value for t in TaskType]
    assert all(row['description'] for row in response.json())


def test_each_task_type_lists_the_successors_its_completion_queues(client):
    """The Rerun Agent dialog draws what a re-run sets in motion from these
    edges, so they must be the worker's own (TASK_SUCCESSORS), by value."""
    rows = {row['type']: row['successors'] for row in client.get('/task-types').json()}

    assert rows['Variant Extraction'] == [
        'Variant Harmonization',
        'Patient Variant Occurrences',
    ]
    assert rows['Extraction Verification'] == []
    for task_type in TaskType:
        assert rows[task_type.value] == [
            s.value for s in TASK_SUCCESSORS.get(task_type, [])
        ]


def test_a_description_is_one_sentence():
    """The Rerun Agent dialog shows it as a line of help text."""
    for task_type in TaskType:
        text = task_type.description
        assert text.endswith('.'), task_type
        assert '. ' not in text.rstrip('.'), task_type
