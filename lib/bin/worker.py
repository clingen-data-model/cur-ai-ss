#!/usr/bin/env python3
import asyncio
import datetime
import logging
import os
import signal
import time
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from lib.api.db import session_scope
from lib.core.agents_init import init_agents_sdk
from lib.core.email import send_email
from lib.core.environment import env
from lib.core.logging import setup_logging
from lib.misc.snapshots import write_snapshot_safe
from lib.models import TaskDB
from lib.models.flag import FlagDB
from lib.models.paper import PaperDB
from lib.reference_data.hpo import warm_term_lookup_if_cached
from lib.tasks.agent_session import clear_task_session, closing_sessions
from lib.tasks.handlers import TASK_HANDLERS
from lib.tasks.hpo_link_cache import get_hpo_link_cache
from lib.tasks.misc import enqueue_successors, enqueue_task
from lib.tasks.models import (
    ACTIVE_STATUSES,
    CLAIMED_STATUSES,
    TERMINAL_TASK_TYPES,
    TaskStatus,
    TaskType,
)

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

# Prompt-cache warm-up window for the fan-out gate below: a little under the
# 1h TTL the breakpoints use (lib/agents/model_factory.py), so a batch that
# starts inside the window can trust the entry is still there.
CACHE_WARM_S = 50 * 60

setup_logging()
init_agents_sdk()
logger = logging.getLogger(__name__)

try:
    warm_term_lookup_if_cached()
except Exception:
    logger.warning('Failed to warm the HPO term lookup cache at startup', exc_info=True)

try:
    get_hpo_link_cache()
except Exception:
    # Loads lazily on first use instead.
    logger.warning('Failed to load the HPO link cache at startup', exc_info=True)


# Set by the shutdown signal. The poller stops claiming on it, execute_task
# declines to start on it, and the final sweep can then reset every claimed
# row knowing nothing will claim another behind its back.
_shutting_down = False
# Held for the length of a poll, so the shutdown sweep waits for a poll that
# was mid-claim when the signal arrived rather than racing its commit.
_poll_lock = asyncio.Lock()


async def _sweep_claimed_tasks(event: str) -> int:
    """Release every QUEUED or RUNNING task, on shutdown and again on startup.

    This is the only worker process, so at either moment a claimed row can
    belong to no live run: on shutdown they are all this process's, and it is
    about to exit; on startup they are whatever the last process left, which
    is nothing when it shut down in order and everything it held when it was
    killed outright. Resetting them all is therefore exact, and it needs no
    bookkeeping of which rows this process holds -- the in-memory set it
    replaced missed tasks still waiting on a semaphore and tasks claimed by a
    poll that ran during the shutdown itself, which then sat RUNNING until the
    lease timeout.

    Same reset, and same PENDING-vs-abandon retry check, that the lease
    timeout applies: PENDING with a cleared session, so the retry starts from
    a clean slate rather than piling a fresh prompt onto an interrupted one.
    The status write is one transaction with no await inside, so a handler
    completing at the same instant lands wholly before or wholly after it.
    Returns the number of rows touched."""
    now = datetime.datetime.now(datetime.timezone.utc)
    to_clear: list[int] = []
    swept = 0
    with session_scope() as session:
        claimed = (
            session.query(TaskDB).filter(TaskDB.status.in_(CLAIMED_STATUSES)).all()
        )
        for task in claimed:
            swept += 1
            # A QUEUED task never started its attempt (tries counts starts),
            # so it has nothing to clear and no attempt to count against it.
            if task.status == TaskStatus.QUEUED or task.tries < MAX_RETRIES:
                if task.status == TaskStatus.RUNNING:
                    to_clear.append(task.id)
                task.status = TaskStatus.PENDING
            else:
                task.status = TaskStatus.FAILED
                task.error_message = f'Worker {event} mid-task and exhausted retries'
            task.updated_at = now
    if swept:
        logger.info(f'Worker {event}: released {swept} claimed task(s)')
    for task_id in to_clear:
        await clear_task_session(task_id)
    return swept


async def _shutdown() -> None:
    try:
        async with _poll_lock:
            await _sweep_claimed_tasks('shut down')
    finally:
        os._exit(0)


def _handle_shutdown_signal(sig: int) -> None:
    global _shutting_down
    if _shutting_down:
        return  # systemd delivers the signal to the whole group; one sweep is enough
    _shutting_down = True
    logger.info(f'Received signal {sig}, releasing claimed tasks before shutdown')
    asyncio.create_task(_shutdown())


async def execute_task(task_id: int) -> None:
    """Execute a single task handler."""
    if _shutting_down:
        # Leave the row QUEUED for the sweep rather than start an attempt the
        # exit is about to kill, which would cost it a try.
        return
    # Mark task as RUNNING, then close session before async work
    task_type = None
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            logger.warning(f'Task {task_id} not found')
            return

        started = datetime.datetime.now(datetime.timezone.utc)
        task.status = TaskStatus.RUNNING
        # Both, deliberately: updated_at is overwritten when the task reaches a
        # terminal status, which is what makes it the finish time. started_at is
        # the only record of when the attempt began, and a retry re-stamps it so
        # the pair always describes the same attempt.
        task.started_at = started
        task.updated_at = started
        task.tries += 1
        task_type = task.type

    # Handler manages its own session - no session held across async boundaries
    handler = TASK_HANDLERS[task_type]
    error_msg = None
    try:
        # Whatever agent sessions the handler opens are closed when it returns
        # (their connections live on executor threads; see agent_session.py).
        with closing_sessions():
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
            # Before the snapshot and the email: a verification row queued
            # here is in flight, so both wait for it (see TERMINAL_TASK_TYPES).
            _maybe_queue_verification(session, task)
            if error_msg is None and task.type in TERMINAL_TASK_TYPES:
                _maybe_write_snapshot(session, task.paper_id)
                _maybe_notify_completion(session, task.paper_id)
            elif error_msg is not None and task.tries > MAX_RETRIES:
                # A final failure can be the last thing a pipeline does.
                _maybe_write_snapshot(session, task.paper_id)


def _maybe_queue_verification(session: Session, task: TaskDB) -> None:
    """Queue the paper's EXTRACTION_VERIFICATION once this completion (or
    final failure) has left every other task settled. Checked on every task,
    not just the graph's leaves: a lone re-run that skips its successors, or
    a pipeline that ends in a failure, settles the paper too. The one row
    per paper is reset in place by enqueue_task, so a paper that settles
    again after a re-run is verified again; a verification that is itself
    running is left alone and the re-run's flags wait for the next settle."""
    if task.type == TaskType.EXTRACTION_VERIFICATION:
        return
    if task.status == TaskStatus.FAILED and task.tries <= MAX_RETRIES:
        return  # still owed a retry
    if not _pipeline_idle(
        session, task.paper_id, ignoring=TaskType.EXTRACTION_VERIFICATION
    ):
        return
    enqueue_task(
        session,
        paper_id=task.paper_id,
        task_type=TaskType.EXTRACTION_VERIFICATION,
        updated_by_user_id=task.updated_by_user_id,
    )


def _pipeline_idle(
    session: Session, paper_id: int, ignoring: TaskType | None = None
) -> bool:
    """Whether no pipeline task of the paper is in flight or owed a retry.

    Idle, not all-COMPLETED: a paper whose pipeline ended with a failed task
    is just as settled. ``ignoring`` leaves one type out of the question --
    the verification row, when deciding whether to queue it."""
    # The session runs with autoflush=False, and the caller has just set the
    # completing task's status to COMPLETED in memory only. Without this flush
    # the query below reads the stale RUNNING row and the check can never pass
    # for the final task of a pipeline -- the exact task meant to trigger it.
    session.flush()
    query = session.query(TaskDB.id).filter(
        TaskDB.paper_id == paper_id,
        or_(
            TaskDB.status.in_(ACTIVE_STATUSES),
            # Still owed a retry by poll_and_schedule_tasks.
            (TaskDB.status == TaskStatus.FAILED) & (TaskDB.tries <= MAX_RETRIES),
        ),
    )
    if ignoring is not None:
        query = query.filter(TaskDB.type != ignoring)
    return query.first() is None


def _maybe_write_snapshot(session: Session, paper_id: int) -> None:
    """Snapshot the paper's extracted state once no pipeline task is in flight.

    Several terminal tasks can finish in quick succession; write_snapshot
    dedupes on a state hash, so repeat calls for an unchanged paper are no-ops.
    A snapshot failure must never fail the task bookkeeping around it."""
    if _pipeline_idle(session, paper_id):
        write_snapshot_safe(session, paper_id)


def _maybe_notify_completion(session: Session, paper_id: int) -> None:
    """Email the paper's owner the first time its pipeline finishes.

    Unlike _maybe_write_snapshot, fires only once every pipeline task is
    COMPLETED, and does not share its tolerance for repeat calls: that dedupes
    on a state hash, whereas a second email is simply a second email. The
    condition stays true once it passes and is re-checked on every terminal
    task, so papers.completion_notified_at is what makes this fire exactly once.

    The recipient is the paper's updated_by user. That is the uploader at upload
    time and the last editor afterwards; in practice the pipeline finishes
    before anyone can meaningfully edit extractions that do not exist yet, so at
    this moment it is almost always the person who queued it.

    A mail failure must never fail the task bookkeeping around it, so everything
    here is best-effort -- but the row is only stamped after send_email returns,
    so a transient SMTP outage leaves the paper eligible on the next terminal
    task rather than silently swallowing the notification.
    """
    session.flush()  # see _maybe_write_snapshot: the caller's status is in-memory only
    paper = session.get(PaperDB, paper_id)
    if paper is None or paper.completion_notified_at is not None:
        return

    pipeline_statuses = [
        task_status
        for (task_status,) in session.query(TaskDB.status).filter(
            TaskDB.paper_id == paper_id
        )
    ]
    if not pipeline_statuses or not all(
        s == TaskStatus.COMPLETED for s in pipeline_statuses
    ):
        return

    user = paper.updated_by
    if user is None or not user.notify_on_paper_complete or not user.email:
        # Still stamp: the pipeline did complete, and flipping the preference on
        # later should not retroactively mail about work already finished.
        paper.completion_notified_at = datetime.datetime.now(datetime.timezone.utc)
        return

    title = paper.title or paper.filename
    open_flags = (
        session.query(FlagDB)
        .filter(FlagDB.paper_id == paper_id, FlagDB.resolved_at.is_(None))
        .count()
    )
    link = f'{env.PROTOCOL}{env.API_ENDPOINT}/papers/{paper_id}/extraction'
    if open_flags:
        link += '?tab=flags'
    flags_line = (
        f'{open_flags} flag{"" if open_flags == 1 else "s"} to review.\n\n'
        if open_flags
        else ''
    )
    try:
        send_email(
            to=user.email,
            subject=f'Extraction complete: {title}',
            body=(
                f'Extraction finished for "{title}".\n\n'
                f'{flags_line}'
                f'{link}\n\n'
                'You are receiving this because paper completion notifications '
                'are enabled in your settings.'
            ),
        )
    except Exception:
        logger.exception(
            f'Failed to send completion email for paper {paper_id}; '
            f'leaving it eligible for retry'
        )
        return

    paper.completion_notified_at = datetime.datetime.now(datetime.timezone.utc)


# Fan-out gate, keyed by (paper, task type). Anthropic makes a prompt-cache
# entry available only once the first response that wrote it has begun, so if
# the 25 demographics tasks of a paper all start at once every one of them
# writes the paper prefix and none reads it. The first task of a paper+type
# runs alone; the rest wait on its lock, find the gate warm, and run together
# under the ordinary semaphores. Costs one task's latency per paper+type per
# warm window, for every provider (no branch to keep in step with the model
# config; OpenAI's automatic caching likes a warmed prefix just as much).
_fanout_gates: dict[tuple[int, TaskType], asyncio.Lock] = {}
_warm_until: dict[tuple[int, TaskType], float] = {}


def _gate_is_warm(key: tuple[int, TaskType]) -> bool:
    return _warm_until.get(key, 0.0) > time.monotonic()


async def execute_task_with_semaphore(
    task_id: int,
    global_semaphore: asyncio.Semaphore,
    type_semaphore: asyncio.Semaphore,
    paper_id: int | None = None,
    task_type: TaskType | None = None,
) -> None:
    """Execute task, respecting global and type-specific concurrency limits
    and the per-paper fan-out gate (when the caller says which paper+type)."""
    async with global_semaphore, type_semaphore:
        if paper_id is None or task_type is None:
            await execute_task(task_id)
            return
        key = (paper_id, task_type)
        lock = _fanout_gates.setdefault(key, asyncio.Lock())
        async with lock:
            if not _gate_is_warm(key):
                try:
                    await execute_task(task_id)
                finally:
                    # Success or failure, the request went out and wrote the
                    # prefix; a retry must not serialise the others again.
                    _warm_until[key] = time.monotonic() + CACHE_WARM_S
                return
        await execute_task(task_id)


async def poll_and_schedule_tasks(
    global_semaphore: asyncio.Semaphore,
    semaphores: dict[TaskType, asyncio.Semaphore],
) -> None:
    """Poll for pending tasks and schedule them (non-blocking)."""
    async with _poll_lock:
        if _shutting_down:
            return
        await _poll_and_schedule_tasks(global_semaphore, semaphores)


async def _poll_and_schedule_tasks(
    global_semaphore: asyncio.Semaphore,
    semaphores: dict[TaskType, asyncio.Semaphore],
) -> None:
    with session_scope() as session:
        now = datetime.datetime.now(datetime.timezone.utc)
        expired_cutoff = now - datetime.timedelta(seconds=LEASE_TIMEOUT_S)

        # Reset timed-out claimed tasks back to PENDING (only if retries remain)
        timed_out_tasks = (
            session.query(TaskDB)
            .filter(
                TaskDB.status.in_(CLAIMED_STATUSES),
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
                await clear_task_session(task.id)
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
            await clear_task_session(task.id)

        session.flush()

        # Fetch pending tasks grouped by type
        pending_tasks: dict[TaskType, list[tuple[int, int]]] = {}
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
                pending_tasks[task_type] = [(t.id, t.paper_id) for t in tier_tasks]
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
    for task_type, tasks in pending_tasks.items():
        for task_id, paper_id in tasks:
            asyncio.create_task(
                execute_task_with_semaphore(
                    task_id,
                    global_semaphore,
                    semaphores[task_type],
                    paper_id=paper_id,
                    task_type=task_type,
                )
            )
            total_scheduled += 1
    logger.info(f'Scheduled {total_scheduled} tasks')


async def main_async() -> None:
    """Main async loop: continuously poll for tasks and schedule them."""
    # add_signal_handler (not signal.signal) so the handler can schedule the
    # async release above on this same loop rather than running as a plain
    # synchronous interrupt.
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_shutdown_signal, sig)

    # Create global and type-specific semaphores
    global_semaphore = asyncio.Semaphore(GLOBAL_CONCURRENCY)
    semaphores: dict[TaskType, asyncio.Semaphore] = {}
    for task_type in TaskType:
        limit = TASK_CONCURRENCY.get(task_type, DEFAULT_CONCURRENCY)
        semaphores[task_type] = asyncio.Semaphore(limit)

    logger.info('Starting task worker')
    # Whatever the last process left claimed is nobody's now (see the sweep).
    await _sweep_claimed_tasks('restarted')
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
