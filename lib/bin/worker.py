#!/usr/bin/env python3
import asyncio
import datetime
import inspect
import logging
import os
import signal
import time
from types import FrameType
from typing import Any, Callable, Coroutine, Iterable, List

from lib.api.db import session_scope
from lib.core.logging import setup_logging
from lib.models import TaskDB
from lib.tasks.handlers import TASK_HANDLERS
from lib.tasks.misc import enqueue_successors
from lib.tasks.models import TaskStatus, TaskType

LEASE_TIMEOUT_S = 900
POLL_INTERVAL_S = 10
MAX_AGENTIC_TASKS = 5
MAX_RETRIES = 2
RETRY_DELAY_S = 30

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
        if inspect.iscoroutinefunction(handler):
            await handler(task_id)
        else:
            handler(task_id)
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
                enqueue_successors(session, task)
            else:
                task.status = TaskStatus.FAILED
                task.error_message = error_msg


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

        # Now fetch pending tasks
        # Separate PDF_PARSING (CPU-bound, max 1) from other tasks
        pdf_parsing_tasks = (
            session.query(TaskDB)
            .filter(
                TaskDB.type == TaskType.PDF_PARSING,
                TaskDB.status == TaskStatus.PENDING,
            )
            .limit(1)
            .all()
        )

        other_tasks = (
            session.query(TaskDB)
            .filter(
                TaskDB.type != TaskType.PDF_PARSING,
                TaskDB.status == TaskStatus.PENDING,
            )
            .limit(MAX_AGENTIC_TASKS)
            .all()
        )

        all_tasks = pdf_parsing_tasks + other_tasks
        all_task_ids = [t.id for t in all_tasks]

        # Build a map of task type to task objects for logging
        task_type_counts: dict[TaskType, int] = {}
        for task in all_tasks:
            task_type_counts[task.type] = task_type_counts.get(task.type, 0) + 1

    if not all_task_ids:
        logger.info('Found no pending tasks')
        return

    # Build detailed log message with task type breakdown
    type_breakdown = ', '.join(
        f'{count} {task_type}' for task_type, count in sorted(task_type_counts.items())
    )
    logger.info(f'Executing {len(all_task_ids)} tasks: {type_breakdown}')

    try:
        run_async(execute_task, all_task_ids)
    except Exception:
        logger.exception('Error executing task batch')


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
