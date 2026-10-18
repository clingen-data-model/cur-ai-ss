from lib.tasks.models import TaskType


def test_every_task_type_is_listed_with_a_description(client):
    response = client.get('/task-types')

    assert response.status_code == 200
    assert [row['type'] for row in response.json()] == [t.value for t in TaskType]
    assert all(row['description'] for row in response.json())


def test_a_description_is_one_sentence():
    """The Rerun Agent dialog shows it as a line of help text."""
    for task_type in TaskType:
        text = task_type.description
        assert text.endswith('.'), task_type
        assert '. ' not in text.rstrip('.'), task_type
