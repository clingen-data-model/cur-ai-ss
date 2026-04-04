#!/usr/bin/env python3
import asyncio
import datetime
import logging
import os
import signal
import time
from types import FrameType

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
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            logger.warning(f'Task {task_id} not found')
            return

        handler = TASK_HANDLERS[task.type]

        task.status = TaskStatus.RUNNING
        task.tries += 1

        try:
            await handler(session, task)
            task.status = TaskStatus.COMPLETED
            task.error_message = None
            enqueue_successors(session, task)
        except Exception as e:
            logger.exception(f'Task {task.id} ({task.type}) failed')
            task.status = TaskStatus.FAILED
            task.error_message = str(e)


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
        retriable_tasks = (
            session.query(TaskDB)
            .filter(
                TaskDB.status == TaskStatus.FAILED,
                TaskDB.tries <= MAX_RETRIES,
            )
            .all()
        )
        for task in retriable_tasks:
            logger.info(
                f'Retrying task {task.id} ({task.type}) (attempt {task.tries + 1}/{MAX_RETRIES})'
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

        all_task_ids = [t.id for t in pdf_parsing_tasks + other_tasks]
        pdf_parsing_count = len(pdf_parsing_tasks)

    if not all_task_ids:
        logger.info('Found no pending tasks')
        return

    logger.info(
        f'Executing {len(all_task_ids)} tasks ({pdf_parsing_count} PDF parsing, {len(all_task_ids) - pdf_parsing_count} other)'
    )

    try:
        coros = [execute_task(task_id) for task_id in all_task_ids]
        asyncio.run(asyncio.gather(*coros))  # type: ignore[arg-type]
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
