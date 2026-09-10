"""Tasks tab: the pipeline queue for a single paper."""

from typing import Any

import pandas as pd
import streamlit as st

from lib.models import PaperResp
from lib.tasks import TaskResp, TaskStatus, TaskType
from lib.tasks.models import TASK_SUCCESSORS

# Icons follow the paper status badge (see get_status_badge_icon); QUEUED has no
# badge equivalent, so it borrows the amber dot used elsewhere in the UI.
STATUS_ICONS: dict[TaskStatus, str] = {
    TaskStatus.PENDING: '⏹️',
    TaskStatus.QUEUED: '🟡',
    TaskStatus.RUNNING: '⏳',
    TaskStatus.COMPLETED: '✅',
    TaskStatus.FAILED: '❌',
}

_PIPELINE_TYPES: list[TaskType] = list(TaskType)
_DECLARATION_INDEX: dict[TaskType, int] = {
    task_type: index for index, task_type in enumerate(_PIPELINE_TYPES)
}


def _pipeline_depths() -> dict[TaskType, int]:
    """Depth of each task in the dependency graph, so prerequisites sort first.

    TaskType's declaration order calls itself execution order but is not: the
    segregation tasks are declared ahead of Patient Variant Occurrences, which
    TASK_SUCCESSORS makes their prerequisite. Depth is the longest path from a
    root, so a task always follows everything it waits on.
    """
    depths: dict[TaskType, int] = dict.fromkeys(_PIPELINE_TYPES, 0)

    # Small DAG; relax until it settles.
    for _ in range(len(_PIPELINE_TYPES)):
        changed = False
        for task, successors in TASK_SUCCESSORS.items():
            for successor in successors:
                if depths[successor] < depths[task] + 1:
                    depths[successor] = depths[task] + 1
                    changed = True
        if not changed:
            break

    # A type absent from the graph has no prerequisites and would tie with PDF
    # Parsing at depth zero, sorting above the task that actually starts the
    # pipeline. Send those to the end instead. Today the only such member is
    # General Paper Question, which is a chat routing outcome and never queued
    # as a task at all; the guard is really for a task type added here before
    # its successors are wired up.
    connected = set(TASK_SUCCESSORS) | {
        successor for successors in TASK_SUCCESSORS.values() for successor in successors
    }
    tail = max(depths.values(), default=0) + 1
    for task in _PIPELINE_TYPES:
        if task not in connected:
            depths[task] = tail

    return depths


# Depth first, then declaration order so tasks that can run concurrently keep a
# stable, readable grouping.
PIPELINE_ORDER: dict[TaskType, tuple[int, int]] = {
    task_type: (depth, _DECLARATION_INDEX[task_type])
    for task_type, depth in _pipeline_depths().items()
}


def _status_label(status: TaskStatus) -> str:
    """Render a status so it reads at a glance rather than as a bare enum."""
    return f'{STATUS_ICONS.get(status, "•")} {status.value}'


def _scope_label(task: TaskResp) -> str:
    """Summarise which entity a per-entity task is scoped to.

    Most task types run once per paper; the per-patient, per-family and
    per-variant ones repeat, and are indistinguishable in the grid without this.
    """
    scopes = (
        ('Patient', task.patient_id),
        ('Family', task.family_id),
        ('Variant', task.variant_id),
        ('Phenotype', task.phenotype_id),
        ('Occurrence', task.patient_variant_occurrence_id),
    )
    return ', '.join(f'{name} {value}' for name, value in scopes if value is not None)


def _task_rows(tasks: list[TaskResp]) -> list[dict[str, Any]]:
    ordered = sorted(
        tasks,
        key=lambda t: (
            PIPELINE_ORDER.get(t.type, (len(PIPELINE_ORDER), 0)),
            t.updated_at,
            t.id,
        ),
    )
    return [
        {
            'Task Type': task.type.value,
            'Status': _status_label(task.status),
            'Scope': _scope_label(task),
            'Tries': task.tries,
            'Skip Successors': task.skip_successors,
            'Updated': task.updated_at,
            'Updated By': task.updated_by.name if task.updated_by else None,
            'Error': task.error_message,
            'Context': task.additional_context,
            'Task ID': task.id,
        }
        for task in ordered
    ]


def render_tasks_tab() -> None:
    """Display every task queued for this paper, in pipeline order."""
    paper_resp: PaperResp = st.session_state['paper_resp']

    if not paper_resp.tasks:
        st.write('No tasks have been queued for this paper yet...')
        return

    rows = _task_rows(paper_resp.tasks)

    counts = {status: 0 for status in TaskStatus}
    for task in paper_resp.tasks:
        counts[task.status] += 1
    summary = '  ·  '.join(
        f'{STATUS_ICONS[status]} {count} {status.value}'
        for status, count in counts.items()
        if count
    )
    st.caption(f'{len(rows)} tasks  ·  {summary}')

    st.dataframe(
        pd.DataFrame(rows),
        width='stretch',
        hide_index=True,
        column_config={
            'Task Type': st.column_config.TextColumn('Task Type', width='medium'),
            'Status': st.column_config.TextColumn('Status', width='small'),
            'Scope': st.column_config.TextColumn('Scope', width='small'),
            'Tries': st.column_config.NumberColumn('Tries', width='small'),
            'Skip Successors': st.column_config.CheckboxColumn(
                'Skip Successors', width='small'
            ),
            'Updated': st.column_config.DatetimeColumn(
                'Updated', format='YYYY-MM-DD HH:mm:ss', width='medium'
            ),
            'Updated By': st.column_config.TextColumn('Updated By', width='small'),
            'Error': st.column_config.TextColumn('Error', width='large'),
            'Context': st.column_config.TextColumn('Context', width='medium'),
            'Task ID': st.column_config.NumberColumn('Task ID', width='small'),
        },
    )
