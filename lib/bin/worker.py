#!/usr/bin/env python3
import asyncio
import datetime
import logging
import os
import signal
import time
from types import FrameType
from typing import Any, Callable, Coroutine, Iterable, List

from lib.api.db import session_scope
from lib.core.logging import setup_logging
from lib.models import TaskDB
from lib.models.paper import PaperDB
from lib.tasks.handlers import TASK_HANDLERS
from lib.tasks.misc import enqueue_successors
from lib.tasks.models import TaskStatus, TaskType

LEASE_TIMEOUT_S = 900
POLL_INTERVAL_S = 10
MAX_RETRIES = 2
RETRY_DELAY_S = 30

TASK_CONCURRENCY: dict[TaskType, int] = {
    TaskType.PDF_PARSING: 1,
    TaskType.VARIANT_HARMONIZATION: 10,
    TaskType.VARIANT_ANNOTATION: 10,
}
DEFAULT_CONCURRENCY = 20

setup_logging()
logger = logging.getLogger(__name__)


def _signal_handler(sig: int, frame: FrameType | None) -> None:
    """Handle SIGINT and SIGTERM by exiting immediately."""
    logger.info(f'Received signal {sig}, shutting down')
    os._exit(0)


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def run_async(
    fn: Callable[[Any], Coroutine[Any, Any, Any]], items: Iterable[Any]
) -> List[Any]:
    """Run async function on multiple items concurrently.

    Args:
        fn: An async function that takes a single item
        items: Iterable of items to pass to fn

    Returns:
        List of results or exceptions from executing fn on each item
    """

    async def _runner() -> List[Any]:
        return await asyncio.gather(
            *(fn(item) for item in items),
            return_exceptions=True,
        )

    return asyncio.run(_runner())


async def execute_task(task_id: int) -> None:
    """Execute a single task handler."""
    # Mark task as RUNNING, then close session before async work
    task_type = None
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            logger.warning(f'Task {task_id} not found')
            return

        task.status = TaskStatus.RUNNING
        task.tries += 1
        task_type = task.type

    # Handler manages its own session - no session held across async boundaries
    handler = TASK_HANDLERS[task_type]
    error_msg = None
    try:
        await handler(task_id)
    except Exception as e:
        logger.exception(f'Task {task_id} ({task_type}) failed')
        error_msg = str(e)

    # Update final status in a new session
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if task:
            if error_msg is None:
                task.status = TaskStatus.COMPLETED
                task.error_message = None
                if not task.skip_successors:
                    enqueue_successors(session, task)
            else:
                task.status = TaskStatus.FAILED
                task.error_message = error_msg
            paper = session.get(PaperDB, task.paper_id)
            if paper:
                paper.updated_at = datetime.datetime.now(datetime.timezone.utc)


def poll_and_execute_tasks() -> None:
    """Poll for pending tasks and execute them."""
    # Poll and prepare tasks
    with session_scope() as session:
        now = datetime.datetime.utcnow()
        expired_cutoff = now - datetime.timedelta(seconds=LEASE_TIMEOUT_S)

        # Reset timed-out RUNNING tasks back to PENDING
        timed_out_tasks = (
            session.query(TaskDB)
            .filter(
                TaskDB.status == TaskStatus.RUNNING,
                TaskDB.updated_at < expired_cutoff,
            )
            .all()
        )
        for task in timed_out_tasks:
            logger.info(f'Resetting timed-out task {task.id} ({task.type})')
            task.status = TaskStatus.PENDING

        # Reset FAILED tasks that haven't exceeded retry limit back to PENDING
        retry_cutoff = now - datetime.timedelta(seconds=RETRY_DELAY_S)
        retriable_tasks = (
            session.query(TaskDB)
            .filter(
                TaskDB.status == TaskStatus.FAILED,
                TaskDB.tries <= MAX_RETRIES,
                TaskDB.updated_at < retry_cutoff,
            )
            .all()
        )
        for task in retriable_tasks:
            logger.info(
                f'Retrying task {task.id} ({task.type}) (attempt {task.tries + 1}/{MAX_RETRIES + 1})'
            )
            task.status = TaskStatus.PENDING
            task.error_message = None

        session.flush()

        # Fetch pending tasks grouped by concurrency tier
        # Group task types by their concurrency limits
        concurrency_tiers: dict[int, list[TaskType]] = {}
        for task_type in TaskType:
            limit = TASK_CONCURRENCY.get(task_type, DEFAULT_CONCURRENCY)
            if limit not in concurrency_tiers:
                concurrency_tiers[limit] = []
            concurrency_tiers[limit].append(task_type)

        # Fetch tasks for each tier, respecting their concurrency limits
        tasks_by_tier: dict[int, list[int]] = {}
        for limit, task_types in concurrency_tiers.items():
            tier_tasks = (
                session.query(TaskDB)
                .filter(
                    TaskDB.type.in_(task_types),
                    TaskDB.status == TaskStatus.PENDING,
                )
                .limit(limit)
                .all()
            )
            if tier_tasks:
                tasks_by_tier[limit] = [t.id for t in tier_tasks]

    if not tasks_by_tier:
        logger.info('Found no pending tasks')
        return

    # Execute tasks by concurrency tier (low to high)
    # This ensures external DB tasks run before higher-concurrency OpenAI tasks
    for limit in sorted(tasks_by_tier.keys()):
        task_ids = tasks_by_tier[limit]
        logger.info(f'Executing {len(task_ids)} tasks with concurrency limit {limit}')
        try:
            run_async(execute_task, task_ids)
        except Exception:
            logger.exception(f'Error executing task batch with limit {limit}')


def main() -> None:
    logger.info('Starting task worker')
    while True:
        logger.info('Looking for work')
        try:
            poll_and_execute_tasks()
        except Exception:
            logger.exception('Unexpected error in worker loop')
        time.sleep(POLL_INTERVAL_S)


if __name__ == '__main__':
    main()
