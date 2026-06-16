#!/usr/bin/env python3
import asyncio
import datetime
import logging
import os
import signal
from types import FrameType
from typing import Any

from lib.api.db import session_scope
from lib.core.logging import setup_logging
from lib.models import TaskDB
from lib.models.paper import PaperDB
from lib.tasks.handlers import TASK_HANDLERS
from lib.tasks.misc import enqueue_successors
from lib.tasks.models import TaskStatus, TaskType

LEASE_TIMEOUT_S = 1800
POLL_INTERVAL_S = 10
MAX_RETRIES = 2
RETRY_DELAY_S = 30

GLOBAL_CONCURRENCY = 30
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
        task.updated_at = datetime.datetime.now(datetime.timezone.utc)
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
            now = datetime.datetime.now(datetime.timezone.utc)
            if error_msg is None:
                task.status = TaskStatus.COMPLETED
                task.updated_at = now
                task.error_message = None
                if not task.skip_successors:
                    enqueue_successors(session, task)
            else:
                task.status = TaskStatus.FAILED
                task.updated_at = now
                task.error_message = error_msg
            paper = session.get(PaperDB, task.paper_id)
            if paper:
                paper.updated_at = now


async def execute_task_with_semaphore(
    task_id: int,
    global_semaphore: asyncio.Semaphore,
    type_semaphore: asyncio.Semaphore,
) -> None:
    """Execute task, respecting global and type-specific concurrency limits."""
    async with global_semaphore, type_semaphore:
        await execute_task(task_id)


async def poll_and_schedule_tasks(
    global_semaphore: asyncio.Semaphore,
    semaphores: dict[TaskType, asyncio.Semaphore],
) -> None:
    """Poll for pending tasks and schedule them (non-blocking)."""
    with session_scope() as session:
        now = datetime.datetime.now(datetime.timezone.utc)
        expired_cutoff = now - datetime.timedelta(seconds=LEASE_TIMEOUT_S)

        # Reset timed-out RUNNING/QUEUED tasks back to PENDING (only if retries remain)
        timed_out_tasks = (
            session.query(TaskDB)
            .filter(
                TaskDB.status.in_([TaskStatus.RUNNING, TaskStatus.QUEUED]),
                TaskDB.updated_at < expired_cutoff,
            )
            .all()
        )
        for task in timed_out_tasks:
            if task.tries < MAX_RETRIES:
                logger.info(
                    f'Resetting timed-out task {task.id} ({task.type}) (attempt {task.tries + 1}/{MAX_RETRIES + 1})'
                )
                task.status = TaskStatus.PENDING
                task.conversation_id = None
            else:
                logger.info(
                    f'Abandoning timed-out task {task.id} ({task.type}) (exhausted retries at {task.tries})'
                )
                task.status = TaskStatus.FAILED
                task.error_message = (
                    f'Task exceeded lease timeout ({LEASE_TIMEOUT_S}s) and max retries'
                )
            task.updated_at = now

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
            task.updated_at = now
            task.error_message = None
            task.conversation_id = None

        session.flush()

        # Fetch pending tasks grouped by type
        pending_tasks: dict[TaskType, list[int]] = {}
        for task_type in TaskType:
            limit = TASK_CONCURRENCY.get(task_type, DEFAULT_CONCURRENCY)
            tier_tasks = (
                session.query(TaskDB)
                .filter(
                    TaskDB.type == task_type,
                    TaskDB.status == TaskStatus.PENDING,
                )
                .limit(limit)
                .all()
            )
            if tier_tasks:
                pending_tasks[task_type] = [t.id for t in tier_tasks]
                # Mark as QUEUED to prevent re-scheduling before execution
                for task in tier_tasks:
                    task.status = TaskStatus.QUEUED
                    task.updated_at = now

        session.flush()

    if not pending_tasks:
        logger.info('Found no pending tasks')
        return

    # Schedule tasks with global and type-specific semaphores (non-blocking)
    total_scheduled = 0
    for task_type, task_ids in pending_tasks.items():
        for task_id in task_ids:
            asyncio.create_task(
                execute_task_with_semaphore(
                    task_id, global_semaphore, semaphores[task_type]
                )
            )
            total_scheduled += 1
    logger.info(f'Scheduled {total_scheduled} tasks')


async def main_async() -> None:
    """Main async loop: continuously poll for tasks and schedule them."""
    # Create global and type-specific semaphores
    global_semaphore = asyncio.Semaphore(GLOBAL_CONCURRENCY)
    semaphores: dict[TaskType, asyncio.Semaphore] = {}
    for task_type in TaskType:
        limit = TASK_CONCURRENCY.get(task_type, DEFAULT_CONCURRENCY)
        semaphores[task_type] = asyncio.Semaphore(limit)

    logger.info('Starting task worker')
    while True:
        logger.info('Looking for work')
        try:
            await poll_and_schedule_tasks(global_semaphore, semaphores)
        except Exception:
            logger.exception('Unexpected error in worker loop')
        await asyncio.sleep(POLL_INTERVAL_S)


def main() -> None:
    asyncio.run(main_async())


if __name__ == '__main__':
    main()
