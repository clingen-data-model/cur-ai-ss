from typing import Literal

from sqlalchemy.orm import Session

from lib.models.agent_run import AgentRunDB
from lib.models.patient_variant_occurrences import (
    PatientVariantOccurrenceDB,
    Zygosity,
)
from lib.tasks.models import (
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
    patient_variant_occurrence_id: int | None = None,
    skip_successors: bool = False,
    additional_context: str | None = None,
    updated_by_user_id: int | None = None,
) -> TaskDB:
    """Create or reset a task to PENDING status.

    Checks for existing task and updates it, or creates new one.
    If task is currently running, returns it unchanged.
    Returns the task (either newly created or reset).

    ``updated_by_user_id`` records who triggered the task; leave ``None`` for
    machine enqueues (worker successors) so they stay unattributed.
    """
    # Get latest agent run
    latest_run = session.query(AgentRunDB).order_by(AgentRunDB.id.desc()).first()
    if not latest_run:
        raise ValueError('No agent runs found. Create one with ensure_agent_run().')
    agent_run_id = latest_run.id

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
            TaskDB.patient_variant_occurrence_id == patient_variant_occurrence_id,
        )
        .first()
    )

    if existing_task:
        # Skip re-queuing if task is already running or queued
        if existing_task.status in (TaskStatus.RUNNING, TaskStatus.QUEUED):
            return existing_task
        # Reset existing task
        existing_task.status = TaskStatus.PENDING
        existing_task.tries = 0
        existing_task.error_message = None
        existing_task.skip_successors = skip_successors
        existing_task.additional_context = additional_context
        existing_task.updated_by_user_id = updated_by_user_id
        # Clear conversation_id if not providing new context (start fresh).
        if additional_context is None:
            existing_task.conversation_id = None
        session.flush()
        return existing_task
    else:
        # Create new task
        new_task = TaskDB(
            type=task_type,
            paper_id=paper_id,
            agent_run_id=agent_run_id,
            family_id=family_id,
            patient_id=patient_id,
            variant_id=variant_id,
            phenotype_id=phenotype_id,
            patient_variant_occurrence_id=patient_variant_occurrence_id,
            status=TaskStatus.PENDING,
            skip_successors=skip_successors,
            additional_context=additional_context,
            updated_by_user_id=updated_by_user_id,
        )
        session.add(new_task)
        session.flush()
        return new_task


def enqueue_all_instances(
    session: Session,
    paper_id: int,
    task_type: TaskType,
    skip_successors: bool = False,
    additional_context: str | None = None,
    updated_by_user_id: int | None = None,
) -> list[TaskDB]:
    """Re-queue all instances of a task type for a paper.

    If splatted instances exist (with entity IDs), re-queues all of them.
    Otherwise creates/resets a single global task.
    """
    # Find all existing tasks of this type for this paper
    existing_tasks = (
        session.query(TaskDB)
        .filter(
            TaskDB.type == task_type,
            TaskDB.paper_id == paper_id,
        )
        .all()
    )

    if existing_tasks:
        # Re-queue all existing instances, skip if running or queued
        results = []
        for task in existing_tasks:
            if task.status not in (TaskStatus.RUNNING, TaskStatus.QUEUED):
                task.status = TaskStatus.PENDING
                task.tries = 0
                task.error_message = None
                task.skip_successors = skip_successors
                task.additional_context = additional_context
                task.updated_by_user_id = updated_by_user_id
                # Clear conversation_id if not providing new context (start fresh)
                if additional_context is None:
                    task.conversation_id = None
                results.append(task)
        session.flush()
        return results if results else existing_tasks
    else:
        # No existing tasks, create a global one
        task = enqueue_task(
            session,
            paper_id=paper_id,
            task_type=task_type,
            skip_successors=skip_successors,
            additional_context=additional_context,
            updated_by_user_id=updated_by_user_id,
        )
        return [task]


def enqueue_successors(session: Session, task: TaskDB) -> None:
    """Create successor tasks when a task completes.

    Each case is explicit about what successors to create and any entity ID
    filtering/expansion needed. Since the reading passes are separate tasks,
    each feeds only the lookups that need what it produced -- nothing waits on
    an entity it does not use, and no case has to check whether a second
    predecessor has landed.

    The triggering user (``task.updated_by_user_id``) is propagated to successor
    tasks so the attribution chain is preserved end-to-end. Tasks triggered by the
    worker itself (initial pipeline runs) have no user and stay unattributed.
    """
    from lib.models import FamilyDB, PatientDB, PhenotypeDB, VariantDB

    user_id = task.updated_by_user_id

    match task.type:
        case TaskType.PDF_PARSING:
            for task_type in (
                TaskType.PAPER_STRUCTURE,
                TaskType.PEDIGREE_IDENTIFICATION,
            ):
                enqueue_task(
                    session,
                    paper_id=task.paper_id,
                    task_type=task_type,
                    updated_by_user_id=user_id,
                )
            # Bibliographic metadata resolves against PubMed, so it stays its own
            # tool-backed task rather than folding into the one-shot extraction.
            enqueue_task(
                session,
                paper_id=task.paper_id,
                task_type=TaskType.PAPER_METADATA,
                updated_by_user_id=user_id,
            )

        case TaskType.PAPER_STRUCTURE:
            # The three remaining reading passes need this pass and nothing
            # else, so they go out together and the worker runs them in
            # parallel.
            for task_type in (
                TaskType.PATIENT_DETAILS,
                TaskType.PATIENT_GENOTYPES,
                TaskType.SEGREGATION_EVIDENCE,
            ):
                enqueue_task(
                    session,
                    paper_id=task.paper_id,
                    task_type=task_type,
                    updated_by_user_id=user_id,
                )

            # Harmonization needs the variants and nothing else, so it need not
            # wait behind the passes that read the rest of the paper.
            for variant in (
                session.query(VariantDB)
                .filter(VariantDB.paper_id == task.paper_id)
                .all()
            ):
                enqueue_task(
                    session,
                    paper_id=task.paper_id,
                    task_type=TaskType.VARIANT_HARMONIZATION,
                    variant_id=variant.id,
                    updated_by_user_id=user_id,
                )

        case TaskType.PATIENT_DETAILS:
            for phenotype in (
                session.query(PhenotypeDB)
                .filter(PhenotypeDB.paper_id == task.paper_id)
                .all()
            ):
                enqueue_task(
                    session,
                    paper_id=task.paper_id,
                    task_type=TaskType.HPO_LINKING,
                    phenotype_id=phenotype.id,
                    updated_by_user_id=user_id,
                )

        case TaskType.PATIENT_GENOTYPES:
            # The paper-level disease name comes from metadata, which runs in
            # parallel with the whole reading chain; queueing it from both is
            # harmless, since enqueue_task keys on the same scope.
            enqueue_task(
                session,
                paper_id=task.paper_id,
                task_type=TaskType.MONDO_LINKING,
                updated_by_user_id=user_id,
            )

            for occurrence in (
                session.query(PatientVariantOccurrenceDB)
                .filter(PatientVariantOccurrenceDB.paper_id == task.paper_id)
                .all()
            ):
                if not occurrence.disease_name or not occurrence.disease_name.strip():
                    continue
                enqueue_task(
                    session,
                    paper_id=task.paper_id,
                    task_type=TaskType.MONDO_LINKING,
                    patient_variant_occurrence_id=occurrence.id,
                    updated_by_user_id=user_id,
                )

        case TaskType.SEGREGATION_EVIDENCE:
            for family in (
                session.query(FamilyDB).filter(FamilyDB.paper_id == task.paper_id).all()
            ):
                enqueue_task(
                    session,
                    paper_id=task.paper_id,
                    task_type=TaskType.SEGREGATION_ANALYSIS_COMPUTED,
                    family_id=family.id,
                    updated_by_user_id=user_id,
                )

        case TaskType.VARIANT_HARMONIZATION:
            enqueue_task(
                session,
                paper_id=task.paper_id,
                task_type=TaskType.VARIANT_ANNOTATION,
                variant_id=task.variant_id,
                updated_by_user_id=user_id,
            )

        case TaskType.PAPER_METADATA:
            enqueue_task(
                session,
                paper_id=task.paper_id,
                task_type=TaskType.MONDO_LINKING,
            )

        case (
            TaskType.PEDIGREE_IDENTIFICATION
            | TaskType.VARIANT_ANNOTATION
            | TaskType.SEGREGATION_ANALYSIS_COMPUTED
            | TaskType.HPO_LINKING
            | TaskType.MONDO_LINKING
            | TaskType.GENERAL_PAPER_QUESTION
        ):
            # These tasks have no successors
            pass

        case _:
            raise ValueError(
                f'enqueue_successors: unhandled task type {task.type}. '
                'Add a case for this task type.'
            )


def infer_paper_status(tasks: list[TaskResp]) -> InferredPaperStatus:
    """Infer the overall status of a paper from its tasks.

    Returns the inferred status as an enum. Use infer_paper_status_detail()
    for a human-readable detail string with task names and IDs.
    """
    if not tasks:
        return InferredPaperStatus.PENDING

    # Check running or queued tasks
    if any(t.status in (TaskStatus.RUNNING, TaskStatus.QUEUED) for t in tasks):
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

    # Check running or queued tasks
    running_tasks = [
        t for t in tasks if t.status in (TaskStatus.RUNNING, TaskStatus.QUEUED)
    ]
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
