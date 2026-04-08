from typing import Literal

from sqlalchemy.orm import Session

from lib.tasks.models import (
    TASK_PREDECESSORS,
    TASK_SUCCESSORS,
    TaskDB,
    TaskResp,
    TaskStatus,
    TaskType,
)


def enqueue_task(
    session: Session,
    paper_id: int,
    task_type: TaskType,
    patient_id: int | None = None,
    variant_id: int | None = None,
    phenotype_id: int | None = None,
) -> TaskDB:
    """Create or reset a task to PENDING status.

    Checks for existing task and updates it, or creates new one.
    Returns the task (either newly created or reset).
    """
    # Check if task exists (SQLAlchemy converts == None to IS NULL)
    existing_task = (
        session.query(TaskDB)
        .filter(
            TaskDB.type == task_type,
            TaskDB.paper_id == paper_id,
            TaskDB.patient_id == patient_id,
            TaskDB.variant_id == variant_id,
            TaskDB.phenotype_id == phenotype_id,
        )
        .first()
    )

    if existing_task:
        # Reset existing task
        existing_task.status = TaskStatus.PENDING
        existing_task.tries = 0
        existing_task.error_message = None
        session.flush()
        return existing_task
    else:
        # Create new task
        new_task = TaskDB(
            type=task_type,
            paper_id=paper_id,
            patient_id=patient_id,
            variant_id=variant_id,
            phenotype_id=phenotype_id,
            status=TaskStatus.PENDING,
        )
        session.add(new_task)
        session.flush()
        return new_task


def enqueue_successors(session: Session, task: TaskDB) -> None:
    """Create successor tasks when a task completes.

    For each successor task type, checks that ALL predecessor tasks are
    completed before enqueueing. Enqueues with the same paper_id, patient_id,
    variant_id, and phenotype_id.
    """
    successors = TASK_SUCCESSORS.get(task.type, [])

    for successor_type in successors:
        # Check that all predecessors for this successor are completed
        predecessor_types = TASK_PREDECESSORS.get(successor_type, [])
        all_predecessors_done = True

        for pred_type in predecessor_types:
            pred_task = (
                session.query(TaskDB)
                .filter(
                    TaskDB.paper_id == task.paper_id,
                    TaskDB.type == pred_type,
                    TaskDB.patient_id == task.patient_id,
                    TaskDB.variant_id == task.variant_id,
                    TaskDB.phenotype_id == task.phenotype_id,
                )
                .first()
            )
            # If predecessor doesn't exist or isn't completed, skip this successor
            if not pred_task or pred_task.status != TaskStatus.COMPLETED:
                all_predecessors_done = False
                break

        if all_predecessors_done:
            enqueue_task(
                session,
                paper_id=task.paper_id,
                task_type=successor_type,
                patient_id=task.patient_id,
                variant_id=task.variant_id,
                phenotype_id=task.phenotype_id,
            )


def infer_paper_status(tasks: list[TaskResp]) -> str:
    """Infer the overall status of a paper from its tasks.

    Returns a human-readable status string:
    - "N agents running" if multiple tasks running
    - "Task Name Running" or "Task Name for Patient ID/Variant ID Running" if one running
    - "Task Name Failed" for first failed task
    - "Completed" if all done
    - "Pending" if no work started
    """
    if not tasks:
        return 'Pending'

    # Check running tasks
    running_tasks = [t for t in tasks if t.status == TaskStatus.RUNNING]
    if running_tasks:
        if len(running_tasks) > 1:
            return f'{len(running_tasks)} agents running'

        task = running_tasks[0]
        status_str = f'{task.type.value} Running'

        # Add patient/variant identifier if applicable
        if task.patient_id:
            status_str = f'{task.type.value} for Patient {task.patient_id} Running'
        elif task.variant_id:
            status_str = f'{task.type.value} for Variant {task.variant_id} Running'

        return status_str

    # Check failed tasks
    failed_tasks = [t for t in tasks if t.status == TaskStatus.FAILED]
    if failed_tasks:
        task = failed_tasks[0]
        return f'{task.type.value} Failed'

    # Check if all completed
    completed_count = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
    if completed_count == len(tasks):
        return 'Completed'

    # Otherwise pending
    return 'Pending'


def is_task_completed(tasks: list[TaskResp], task_type: TaskType) -> bool:
    """Check if a specific task type is completed in a task list."""
    for task in tasks:
        if task.type == task_type:
            return task.status == TaskStatus.COMPLETED
    return False


def get_status_badge_color(
    tasks: list[TaskResp],
) -> Literal['red', 'blue', 'green', 'gray']:
    """Get color for status badge based on task states."""
    if any(t.status == TaskStatus.FAILED for t in tasks):
        return 'red'
    if any(t.status == TaskStatus.RUNNING for t in tasks):
        return 'blue'
    if all(t.status == TaskStatus.COMPLETED for t in tasks) and tasks:
        return 'green'
    return 'gray'


def get_status_badge_icon(tasks: list[TaskResp]) -> str:
    """Get icon for status badge based on task states."""
    if any(t.status == TaskStatus.RUNNING for t in tasks):
        return '⏳'
    if any(t.status == TaskStatus.FAILED for t in tasks):
        return '❌'
    if all(t.status == TaskStatus.COMPLETED for t in tasks) and tasks:
        return '✅'
    return '⏹️'
