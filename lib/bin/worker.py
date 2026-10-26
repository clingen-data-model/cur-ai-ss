#!/usr/bin/env python3
import asyncio
import datetime
import logging
import os
import signal
from collections import Counter

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
    TERMINAL_TASK_TYPES,
    TaskStatus,
    TaskType,
)

# An attempt's lease runs from started_at and is never refreshed, so the
# timeout must exceed the longest legitimate run of its type or a healthy
# attempt gets retired mid-run and started over. Over 9,500 completed runs on
# dev-caa through 2026-10-22, no agent task passed 13 min; PDF Parsing, whose
# Docling pass scales with page count on a CPU VM, reached 15 min on a 44-page
# supplement.
DEFAULT_LEASE_TIMEOUT_S = 1200
LEASE_TIMEOUT_S: dict[TaskType, int] = {
    TaskType.PDF_PARSING: 1800,
}
POLL_INTERVAL_S = 10
# Retries after the first attempt, so MAX_RETRIES + 1 attempts in all. A row's
# tries counts the attempts started on it, so a row with tries <= MAX_RETRIES
# is still owed a retry and one with tries > MAX_RETRIES has had its last.
# Every check in this module uses that one inequality: the retry sweep, the
# lease and shutdown sweeps, the idle check and the final-failure snapshot.
# The two sweeps used to say "< MAX_RETRIES", which marked a task FAILED
# "exhausted retries" one attempt early and then the retry sweep revived it
# 30 s later anyway.
MAX_RETRIES = 2
RETRY_DELAY_S = 30

# How many attempts may be RUNNING at once, overall and per type. Admission
# is decided from the table on every poll (see _poll_and_schedule_tasks): a
# task is claimed only when a slot is free, and claiming it is starting it.
GLOBAL_CONCURRENCY = 30
TASK_CONCURRENCY: dict[TaskType, int] = {
    TaskType.PDF_PARSING: 1,
    TaskType.VARIANT_HARMONIZATION: 10,
    TaskType.VARIANT_ANNOTATION: 10,
}
DEFAULT_CONCURRENCY = 20

# Prompt-cache warm-up window for the fan-out gate in admission: a little
# under the 1h TTL the breakpoints use (lib/agents/model_factory.py), so a
# batch that starts inside the window can trust the entry is still there.
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
# declines to run an attempt the sweep is about to retire, and the final sweep
# can then reset every claimed row knowing nothing will claim another behind
# its back.
_shutting_down = False
# Held for the length of a poll, so the shutdown sweep waits for a poll that
# was mid-claim when the signal arrived rather than racing its commit.
_poll_lock = asyncio.Lock()
# The coroutine running each live attempt, keyed by (task id, attempt number),
# so the lease sweep can cancel the attempt it retires instead of leaving it
# to run on beside its retry. Keeping the handle is also what asyncio asks
# for: the loop holds only weak references to its tasks, so one nobody keeps
# can be collected mid-run.
_attempts: dict[tuple[int, int], asyncio.Task[None]] = {}


def _launch(task_id: int, attempt: int) -> None:
    key = (task_id, attempt)
    handle = asyncio.create_task(execute_task(task_id, attempt))
    _attempts[key] = handle

    def _forget(done: asyncio.Task[None]) -> None:
        if _attempts.get(key) is done:
            del _attempts[key]

    handle.add_done_callback(_forget)


def _cancel_attempt(task_id: int, attempt: int) -> bool:
    """Ask the coroutine running an attempt to stop. True if there was one to
    ask. Cancellation lands at the coroutine's next await, so a handler in
    the middle of a model call stops there, while one that has pushed its
    work to a thread (Docling, in PDF Parsing) runs that work to the end
    before it notices; either way execute_task sees the cancellation and
    writes nothing."""
    handle = _attempts.get((task_id, attempt))
    return handle is not None and handle.cancel()


async def _sweep_claimed_tasks(event: str) -> int:
    """Release every RUNNING task, on shutdown and again on startup.

    This is the only worker process, so at either moment a RUNNING row can
    belong to no live run: on shutdown they are all this process's, and it is
    about to exit; on startup they are whatever the last process left, which
    is nothing when it shut down in order and everything it held when it was
    killed outright. Resetting them all is therefore exact, and it needs no
    bookkeeping of which rows this process holds.

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
        running = (
            session.query(TaskDB).filter(TaskDB.status == TaskStatus.RUNNING).all()
        )
        for task in running:
            swept += 1
            if task.tries <= MAX_RETRIES:
                to_clear.append(task.id)
                task.status = TaskStatus.PENDING
            else:
                task.status = TaskStatus.FAILED
                task.error_message = f'Worker {event} mid-task and exhausted retries'
            task.updated_at = now
    if swept:
        logger.info(f'Worker {event}: released {swept} running task(s)')
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


def start_attempt(task: TaskDB, now: datetime.datetime) -> int:
    """Stamp the start of an attempt on a claimed row and return its number.

    Both timestamps, deliberately: updated_at is overwritten when the task
    reaches a terminal status, which is what makes it the finish time.
    started_at is the only record of when the attempt began, and a retry
    re-stamps it so the pair always describes the same attempt. The number
    (tries after the increment) is the attempt's token: execute_task writes
    an outcome only while the row still carries it."""
    task.status = TaskStatus.RUNNING
    task.started_at = now
    task.updated_at = now
    task.tries += 1
    return task.tries


async def execute_task(task_id: int, attempt: int) -> None:
    """Run the handler for an attempt started by start_attempt and record its
    outcome, unless the row has moved on. The lease sweep retires an attempt
    that ran too long by cancelling its coroutine and resetting its row. The
    cancellation unwinds this function at the handler's next await, with no
    outcome written; the check on the row below is the backstop for an
    attempt the cancel did not reach in time (its handler was in a thread,
    or it returned on the same loop turn): the row's status and tries say
    which attempt is current, and only that one may write. A stale outcome
    is logged and dropped, successors and all."""
    if _shutting_down:
        # The sweep is about to retire this attempt; do not start a handler
        # the exit will kill.
        return
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            logger.warning(f'Task {task_id} not found')
            return
        task_type = task.type

    # Handler manages its own session - no session held across async boundaries
    handler = TASK_HANDLERS[task_type]
    error_msg = None
    try:
        # Whatever agent sessions the handler opens are closed when it returns
        # (their connections live on executor threads; see agent_session.py).
        with closing_sessions():
            await handler(task_id)
    except asyncio.CancelledError:
        # Retired by the lease sweep, which has already reset the row.
        logger.info(f'Attempt {attempt} of task {task_id} ({task_type}) was cancelled')
        raise
    except Exception as e:
        logger.exception(f'Task {task_id} ({task_type}) failed')
        error_msg = str(e)

    # Update final status in a new session
    with session_scope() as session:
        task = session.get(TaskDB, task_id)
        if not task:
            return
        if task.status != TaskStatus.RUNNING or task.tries != attempt:
            logger.warning(
                f'Attempt {attempt} of task {task_id} ({task_type}) was retired '
                f'while it ran (row is {task.status}, tries {task.tries}); '
                f'dropping its outcome'
            )
            return
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


def lease_timeout_s(task_type: TaskType) -> int:
    return LEASE_TIMEOUT_S.get(task_type, DEFAULT_LEASE_TIMEOUT_S)


def _utc(stamp: datetime.datetime) -> datetime.datetime:
    # SQLite hands the column back naive; it was written in UTC.
    return stamp.replace(tzinfo=stamp.tzinfo or datetime.timezone.utc)


async def poll_and_schedule_tasks() -> None:
    """One poll: retire expired attempts, re-queue retries, start what fits."""
    async with _poll_lock:
        if _shutting_down:
            return
        await _poll_and_schedule_tasks()


async def _poll_and_schedule_tasks() -> None:
    """Everything the scheduler knows is in the tasks table, and a poll is
    one transaction over it. Admission is decided from counts of RUNNING rows
    against the limits above, so a task is claimed only when it can start,
    and claiming it is starting it (start_attempt): there is no in-process
    queue, nothing waits for a slot, and an attempt's lease runs from the
    moment it actually began. A freed slot is refilled on the next poll, up
    to POLL_INTERVAL_S later, which against runs of minutes is nothing.

    The fan-out gate is decided here too. Anthropic makes a prompt-cache
    entry available only once the first response that wrote it has begun, so
    if the 25 demographics tasks of a paper all start at once every one of
    them writes the paper prefix and none reads it. A (paper, type) batch
    whose first attempt is RUNNING and has not yet finished admits nothing
    more; once an attempt of the batch has finished, success or failure,
    within CACHE_WARM_S, the rest start together. Costs one task's latency
    per batch per warm window, for every provider (no branch to keep in step
    with the model config; OpenAI's automatic caching likes a warmed prefix
    just as much)."""
    started: list[tuple[int, int]] = []
    with session_scope() as session:
        now = datetime.datetime.now(datetime.timezone.utc)

        # Retire attempts that have outrun their type's lease: cancel the
        # coroutine, then PENDING with a cleared session while retries remain,
        # else FAILED. Should the cancel land late, the coroutine finds the
        # row moved on and drops its outcome (execute_task).
        shortest = min(DEFAULT_LEASE_TIMEOUT_S, *LEASE_TIMEOUT_S.values())
        expired_cutoff = now - datetime.timedelta(seconds=shortest)
        timed_out_tasks = (
            session.query(TaskDB)
            .filter(
                TaskDB.status == TaskStatus.RUNNING,
                TaskDB.started_at < expired_cutoff,
            )
            .all()
        )
        for task in timed_out_tasks:
            timeout_s = lease_timeout_s(task.type)
            if task.started_at is None or _utc(
                task.started_at
            ) >= now - datetime.timedelta(seconds=timeout_s):
                continue
            cancelled = ', cancelled' if _cancel_attempt(task.id, task.tries) else ''
            if task.tries <= MAX_RETRIES:
                logger.info(
                    f'Retiring timed-out attempt {task.tries} of task {task.id} ({task.type}){cancelled} (attempt {task.tries + 1}/{MAX_RETRIES + 1} next)'
                )
                task.status = TaskStatus.PENDING
                await clear_task_session(task.id)
            else:
                logger.info(
                    f'Abandoning timed-out task {task.id} ({task.type}){cancelled} (exhausted retries at {task.tries})'
                )
                task.status = TaskStatus.FAILED
                task.error_message = (
                    f'Task exceeded lease timeout ({timeout_s}s) and max retries'
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

        # Admission: what is running, and which batches are warm.
        running = session.query(TaskDB).filter(TaskDB.status == TaskStatus.RUNNING)
        total = 0
        by_type: Counter[TaskType] = Counter()
        running_batches: set[tuple[int, TaskType]] = set()
        for task in running:
            total += 1
            by_type[task.type] += 1
            running_batches.add((task.paper_id, task.type))
        warm_since = now - datetime.timedelta(seconds=CACHE_WARM_S)
        warm_batches = {
            (paper_id, task_type)
            for paper_id, task_type in session.query(TaskDB.paper_id, TaskDB.type)
            .filter(
                TaskDB.status.in_((TaskStatus.COMPLETED, TaskStatus.FAILED)),
                TaskDB.updated_at >= warm_since,
            )
            .distinct()
        }

        for task_type in TaskType:
            free = (
                TASK_CONCURRENCY.get(task_type, DEFAULT_CONCURRENCY)
                - by_type[task_type]
            )
            if free <= 0 or total >= GLOBAL_CONCURRENCY:
                continue
            pending = (
                session.query(TaskDB)
                .filter(TaskDB.type == task_type, TaskDB.status == TaskStatus.PENDING)
                .order_by(TaskDB.id)
            )
            for task in pending:
                if free <= 0 or total >= GLOBAL_CONCURRENCY:
                    break
                batch = (task.paper_id, task_type)
                if batch in running_batches and batch not in warm_batches:
                    continue  # the batch's first attempt is still warming the cache
                started.append((task.id, start_attempt(task, now)))
                running_batches.add(batch)
                free -= 1
                total += 1

        session.flush()

    if not started:
        logger.info('Found no pending tasks')
        return

    for task_id, attempt in started:
        _launch(task_id, attempt)
    logger.info(f'Started {len(started)} tasks')


async def main_async() -> None:
    """Main async loop: poll the table and start what fits, forever."""
    # add_signal_handler (not signal.signal) so the handler can schedule the
    # async release above on this same loop rather than running as a plain
    # synchronous interrupt.
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_shutdown_signal, sig)

    logger.info('Starting task worker')
    # Whatever the last process left claimed is nobody's now (see the sweep).
    await _sweep_claimed_tasks('restarted')
    while True:
        logger.info('Looking for work')
        try:
            await poll_and_schedule_tasks()
        except Exception:
            logger.exception('Unexpected error in worker loop')
        await asyncio.sleep(POLL_INTERVAL_S)


def main() -> None:
    asyncio.run(main_async())


if __name__ == '__main__':
    main()
