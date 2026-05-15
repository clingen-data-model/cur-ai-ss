from typing import Literal

from sqlalchemy.orm import Session

from lib.tasks.models import (
    TASK_PREDECESSORS,
    TASK_SUCCESSORS,
    InferredPaperStatus,
    TaskDB,
    TaskResp,
    TaskStatus,
    TaskType,
)


def enqueue_task(
    session: Session,
    paper_id: int,
    task_type: TaskType,
    family_id: int | None = None,
    patient_id: int | None = None,
    variant_id: int | None = None,
    phenotype_id: int | None = None,
    skip_successors: bool = False,
    additional_context: str | None = None,
) -> TaskDB:
    """Create or reset a task to PENDING status.

    Checks for existing task and updates it, or creates new one.
    If task is currently running, returns it unchanged.
    Returns the task (either newly created or reset).
    """
    # Check if task exists (SQLAlchemy converts == None to IS NULL)
    existing_task = (
        session.query(TaskDB)
        .filter(
            TaskDB.type == task_type,
            TaskDB.paper_id == paper_id,
            TaskDB.family_id == family_id,
            TaskDB.patient_id == patient_id,
            TaskDB.variant_id == variant_id,
            TaskDB.phenotype_id == phenotype_id,
        )
        .first()
    )

    if existing_task:
        # Skip re-queuing if task is already running
        if existing_task.status == TaskStatus.RUNNING:
            return existing_task
        # Reset existing task
        existing_task.status = TaskStatus.PENDING
        existing_task.tries = 0
        existing_task.error_message = None
        existing_task.skip_successors = skip_successors
        existing_task.additional_context = additional_context
        session.flush()
        return existing_task
    else:
        # Create new task
        new_task = TaskDB(
            type=task_type,
            paper_id=paper_id,
            family_id=family_id,
            patient_id=patient_id,
            variant_id=variant_id,
            phenotype_id=phenotype_id,
            status=TaskStatus.PENDING,
            skip_successors=skip_successors,
            additional_context=additional_context,
        )
        session.add(new_task)
        session.flush()
        return new_task


def enqueue_successors(session: Session, task: TaskDB) -> None:
    """Create successor tasks when a task completes.

    For each successor task type, checks that ALL predecessor tasks are
    completed before enqueueing. For successors that require entity expansion,
    creates per-entity tasks instead of global ones.
    """
    from lib.models import FamilyDB, PatientDB, PhenotypeDB, VariantDB

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
                )
                .first()
            )
            # If predecessor doesn't exist or isn't completed, skip this successor
            if not pred_task or pred_task.status != TaskStatus.COMPLETED:
                all_predecessors_done = False
                break

            # Check that predecessor's entity IDs match (or predecessor is global)
            if (
                (
                    pred_task.family_id is not None
                    and pred_task.family_id != task.family_id
                )
                or (
                    pred_task.patient_id is not None
                    and pred_task.patient_id != task.patient_id
                )
                or (
                    pred_task.variant_id is not None
                    and pred_task.variant_id != task.variant_id
                )
                or (
                    pred_task.phenotype_id is not None
                    and pred_task.phenotype_id != task.phenotype_id
                )
            ):
                all_predecessors_done = False
                break

        if not all_predecessors_done:
            continue

        # Handle entity expansion for transitions that need per-entity tasks
        if successor_type == TaskType.VARIANT_HARMONIZATION:
            # VARIANT_EXTRACTION (global) -> VARIANT_HARMONIZATION (per-variant)
            variants = (
                session.query(VariantDB)
                .filter(VariantDB.paper_id == task.paper_id)
                .all()
            )
            for variant in variants:
                enqueue_task(
                    session,
                    paper_id=task.paper_id,
                    task_type=successor_type,
                    variant_id=variant.id,
                )
        elif successor_type == TaskType.PHENOTYPE_EXTRACTION:
            # PATIENT_EXTRACTION (global) -> PHENOTYPE_EXTRACTION (per-patient)
            patients = (
                session.query(PatientDB)
                .filter(PatientDB.paper_id == task.paper_id)
                .all()
            )
            for patient in patients:
                enqueue_task(
                    session,
                    paper_id=task.paper_id,
                    task_type=successor_type,
                    patient_id=patient.id,
                )
        elif successor_type == TaskType.HPO_LINKING:
            # PHENOTYPE_EXTRACTION (per-patient) -> HPO_LINKING (per-phenotype)
            phenotypes = (
                session.query(PhenotypeDB)
                .filter(PhenotypeDB.paper_id == task.paper_id)
                .all()
            )
            for phenotype in phenotypes:
                enqueue_task(
                    session,
                    paper_id=task.paper_id,
                    task_type=successor_type,
                    phenotype_id=phenotype.id,
                )
        elif successor_type == TaskType.SEGREGATION_EVIDENCE_EXTRACTION:
            # PATIENT_VARIANT_LINKING (global) -> SEGREGATION_EVIDENCE_EXTRACTION (per-family)
            families = (
                session.query(FamilyDB).filter(FamilyDB.paper_id == task.paper_id).all()
            )
            for family in families:
                enqueue_task(
                    session,
                    paper_id=task.paper_id,
                    task_type=successor_type,
                    family_id=family.id,
                )
        else:
            # For all other successors, pass through the same entity IDs
            enqueue_task(
                session,
                paper_id=task.paper_id,
                task_type=successor_type,
                family_id=task.family_id,
                patient_id=task.patient_id,
                variant_id=task.variant_id,
                phenotype_id=task.phenotype_id,
            )


def infer_paper_status(tasks: list[TaskResp]) -> InferredPaperStatus:
    """Infer the overall status of a paper from its tasks.

    Returns the inferred status as an enum. Use infer_paper_status_detail()
    for a human-readable detail string with task names and IDs.
    """
    if not tasks:
        return InferredPaperStatus.PENDING

    # Check running tasks
    if any(t.status == TaskStatus.RUNNING for t in tasks):
        return InferredPaperStatus.RUNNING

    # Check failed tasks
    if any(t.status == TaskStatus.FAILED for t in tasks):
        return InferredPaperStatus.FAILED

    # Check if all completed
    completed_count = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
    if completed_count == len(tasks):
        return InferredPaperStatus.COMPLETED

    # Otherwise pending
    return InferredPaperStatus.PENDING


def infer_paper_status_detail(tasks: list[TaskResp]) -> str:
    """Get a detailed human-readable status string for display purposes.

    Returns strings like:
    - "N agents running" if multiple tasks running
    - "Task Name Running" or "Task Name for Patient ID/Variant ID Running" if one running
    - "Task Name Failed" for first failed task
    - "Completed" if all done
    - "Pending" if no work started, or "Last Task Name Completed" if some tasks are done
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

    # Pending with completed tasks: show last completed task
    if completed_count > 0:
        completed_tasks = sorted(
            [t for t in tasks if t.status == TaskStatus.COMPLETED],
            key=lambda t: t.updated_at,
            reverse=True,
        )
        last_task = completed_tasks[0]
        return f'{last_task.type.value} Completed'

    # No work started
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
    """Get color for status badge based on paper status."""
    status = infer_paper_status(tasks)
    match status:
        case InferredPaperStatus.RUNNING:
            return 'blue'
        case InferredPaperStatus.FAILED:
            return 'red'
        case InferredPaperStatus.COMPLETED:
            return 'green'
        case InferredPaperStatus.PENDING:
            return 'gray'


def get_status_badge_icon(tasks: list[TaskResp]) -> str:
    """Get icon for status badge based on paper status."""
    status = infer_paper_status(tasks)
    match status:
        case InferredPaperStatus.RUNNING:
            return '⏳'
        case InferredPaperStatus.FAILED:
            return '❌'
        case InferredPaperStatus.COMPLETED:
            return '✅'
        case InferredPaperStatus.PENDING:
            return '⏹️'


def get_all_successor_levels(task_type: TaskType) -> list[list[TaskType]]:
    """Get all successors organized by level (breadth-first).

    Returns a list of lists, where each inner list contains tasks at that level
    in the dependency chain. For example, if PDF_PARSING triggers PAPER_METADATA
    and VARIANT_EXTRACTION, which then trigger their own successors, this returns
    [[PAPER_METADATA, VARIANT_EXTRACTION], [next level...]].
    """
    levels: list[list[TaskType]] = []
    current_level = [task_type]
    seen = {task_type}

    while current_level:
        next_level: list[TaskType] = []
        for task in current_level:
            successors = TASK_SUCCESSORS.get(task, [])
            for successor in successors:
                if successor not in seen:
                    next_level.append(successor)
                    seen.add(successor)

        if next_level:
            levels.append(next_level)
        current_level = next_level

    return levels
