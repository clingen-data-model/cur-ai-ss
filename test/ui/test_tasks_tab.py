from datetime import UTC, datetime, timedelta

from lib.tasks import TaskResp, TaskStatus, TaskType
from lib.ui.paper.shared import TAB_TASKS
from lib.ui.paper.tasks import (
    STATUS_ICONS,
    _scope_label,
    _status_label,
    _task_rows,
)


def _task(task_type: TaskType, **overrides) -> TaskResp:
    fields = {
        'id': 1,
        'paper_id': 1,
        'type': task_type,
        'status': TaskStatus.COMPLETED,
        'tries': 1,
        'error_message': None,
        'skip_successors': False,
        'conversation_id': None,
        'additional_context': None,
        'family_id': None,
        'patient_id': None,
        'variant_id': None,
        'phenotype_id': None,
        'patient_variant_occurrence_id': None,
        'updated_at': datetime(2026, 8, 20, 12, 0, tzinfo=UTC),
    }
    fields.update(overrides)
    return TaskResp(**fields)


def test_every_status_has_an_icon():
    """A missing icon would silently degrade to a bullet."""
    assert set(STATUS_ICONS) == set(TaskStatus)


def test_status_label_is_readable():
    assert _status_label(TaskStatus.FAILED) == '❌ Failed'
    assert _status_label(TaskStatus.QUEUED) == '🟡 Queued'
    # Every status renders as icon + words, never a bare enum.
    for status in TaskStatus:
        label = _status_label(status)
        assert label.endswith(status.value)
        assert label != status.value


def test_scope_label_names_the_entity():
    assert _scope_label(_task(TaskType.HPO_LINKING, patient_id=7)) == 'Patient 7'
    assert _scope_label(_task(TaskType.HPO_LINKING, phenotype_id=3)) == 'Phenotype 3'
    # Paper-wide tasks have no scope.
    assert _scope_label(_task(TaskType.PDF_PARSING)) == ''


def test_every_task_sorts_after_its_prerequisites():
    """The grid must never show a task above something it waits on.

    TaskType declaration order does not satisfy this -- the segregation tasks
    are declared ahead of Patient Variant Occurrences, their prerequisite -- so
    the order is derived from TASK_SUCCESSORS instead. This guards that.
    """
    from lib.tasks.models import TASK_SUCCESSORS
    from lib.ui.paper.tasks import PIPELINE_ORDER

    for task, successors in TASK_SUCCESSORS.items():
        for successor in successors:
            assert PIPELINE_ORDER[task] < PIPELINE_ORDER[successor], (
                f'{task.value} must sort before its successor {successor.value}'
            )


def test_harmonization_sorts_before_annotation():
    """The specific ordering the dependency graph must preserve."""
    from lib.ui.paper.tasks import PIPELINE_ORDER

    assert (
        PIPELINE_ORDER[TaskType.PATIENT_EXTRACTION]
        < PIPELINE_ORDER[TaskType.VARIANT_HARMONIZATION]
        < PIPELINE_ORDER[TaskType.VARIANT_ANNOTATION]
    )


def test_rows_sorted_by_pipeline_order_not_alphabetically():
    """MONDO Linking runs last but sorts first alphabetically."""
    tasks = [
        _task(TaskType.MONDO_LINKING),
        _task(TaskType.PDF_PARSING),
        _task(TaskType.PATIENT_EXTRACTION),
    ]

    types = [row['Task Type'] for row in _task_rows(tasks)]

    assert types == [
        TaskType.PDF_PARSING.value,
        TaskType.PATIENT_EXTRACTION.value,
        TaskType.MONDO_LINKING.value,
    ]


def test_rows_carry_failure_detail():
    rows = _task_rows(
        [
            _task(
                TaskType.HPO_LINKING,
                status=TaskStatus.FAILED,
                tries=3,
                error_message='boom',
                patient_id=2,
            )
        ]
    )

    assert rows[0]['Status'] == '❌ Failed'
    assert rows[0]['Tries'] == 3
    assert rows[0]['Error'] == 'boom'
    assert rows[0]['Scope'] == 'Patient 2'


def test_tasks_tab_offered_with_and_without_chat():
    """Tasks is appended last so existing ?tab_id= deep links keep their target."""
    from types import SimpleNamespace

    from lib.ui.paper.shared import (
        CHAT_FEATURE_GATE_TIME,
        TAB_CHAT,
        TAB_METADATA,
        TAB_OCCURRENCES,
        TAB_PATIENTS,
        TAB_VARIANTS,
        get_available_tabs,
    )

    before = SimpleNamespace(updated_at=CHAT_FEATURE_GATE_TIME - timedelta(days=1))
    after = SimpleNamespace(updated_at=CHAT_FEATURE_GATE_TIME + timedelta(days=1))

    without_chat = get_available_tabs(before)  # type: ignore[arg-type]
    with_chat = get_available_tabs(after)  # type: ignore[arg-type]

    assert TAB_TASKS in without_chat and TAB_TASKS in with_chat
    assert TAB_CHAT not in without_chat and TAB_CHAT in with_chat
    # The four original positions are unchanged in both cases.
    expected = [TAB_METADATA, TAB_PATIENTS, TAB_VARIANTS, TAB_OCCURRENCES]
    assert without_chat[:4] == expected
    assert with_chat[:4] == expected
    assert with_chat.index(TAB_CHAT) == 4
