from datetime import UTC, datetime, timedelta

from lib.tasks import TaskResp, TaskStatus, TaskType
from lib.ui.paper.shared import TAB_TASKS
from lib.ui.paper.tasks import (
    STATUS_ICONS,
    STATUS_WORDS,
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
    # Every status renders as icon + words, never a bare enum.
    for status in TaskStatus:
        label = _status_label(status)
        assert label.endswith(STATUS_WORDS[status])
        assert label != status.value


def test_queued_is_shown_as_pending():
    """QUEUED is the scheduler's claim on a row, not a state the reader of this
    table can act on differently from PENDING -- so it is not shown as its own
    thing."""
    assert _status_label(TaskStatus.QUEUED) == _status_label(TaskStatus.PENDING)


def test_scope_label_names_the_entity():
    assert (
        _scope_label(_task(TaskType.PATIENT_DEMOGRAPHICS, patient_id=7)) == 'Patient 7'
    )
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


def test_segregation_sorts_after_occurrences():
    """The specific inversion that declaration order got wrong."""
    from lib.ui.paper.tasks import PIPELINE_ORDER

    assert (
        PIPELINE_ORDER[TaskType.PATIENT_VARIANT_OCCURRENCES]
        < PIPELINE_ORDER[TaskType.SEGREGATION_EVIDENCE_EXTRACTION]
        < PIPELINE_ORDER[TaskType.SEGREGATION_ANALYSIS_COMPUTED]
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


def test_tab_order_is_stable_for_deep_links():
    """?tab_id= is a positional index into this list.

    So the order is the contract: a tab inserted rather than appended silently
    repoints every existing deep link. Tasks and Chat sit at the end for that
    reason -- both were added after the first four.

    This replaces a pair of tests for CHAT_FEATURE_GATE_TIME, which hid the chat
    tab on papers last updated before 2026-05-17. Every completed task bumps
    papers.updated_at, so the gate cleared itself as papers were re-run, and it
    had stopped excluding anything long before it was removed.
    """
    from lib.ui.paper.shared import (
        PAPER_TABS,
        TAB_CHAT,
        TAB_METADATA,
        TAB_OCCURRENCES,
        TAB_PATIENTS,
        TAB_TASKS,
        TAB_VARIANTS,
    )

    assert PAPER_TABS == [
        TAB_METADATA,
        TAB_OCCURRENCES,
        TAB_PATIENTS,
        TAB_VARIANTS,
        TAB_CHAT,
        TAB_TASKS,
    ]
