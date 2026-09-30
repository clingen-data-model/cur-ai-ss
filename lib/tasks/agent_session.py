"""Local session storage for the additional-context rerun feature.

Every extraction task can be re-run with follow-up feedback (the "Rerun
Agents" popover's "Additional context" field), and the agent needs its prior
turns to make sense of a follow-up. That used to mean OpenAI's Responses API
server-side conversation_id -- a live external dependency that only worked
for openai/ models (LitellmModel ignores conversation_id entirely; see
model_factory.py). This module replaces it with the agents SDK's own
SQLiteSession, stored locally and keyed by the task's own id.

Task rows are reused across reruns rather than recreated (see
lib.tasks.misc.enqueue_task), so the task id is already a stable key -- no
external id needs to be minted or persisted back onto the row.

Connections: the SDK's file-backed session opens one sqlite connection per
thread that touches it, and its database work runs on executor threads
(``asyncio.to_thread``), while its ``close()`` closes only the calling
thread's connection, which the event-loop thread never opened. Left to
itself, every task run therefore parked a couple of open connections on the
worker's executor threads for good; the worker ran out of file descriptors
after ~500 task runs on 2026-09-30 and every later SQLite open in the
process failed. ``TrackedSQLiteSession`` remembers each connection it opens
and closes all of them, and ``closing_sessions`` closes every session a task
opened when the task ends, whether or not the handler kept a handle on it.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from agents.memory import SQLiteSession

from lib.core.environment import env

AGENT_SESSIONS_DB_NAME = 'agent_sessions.db'


class TrackedSQLiteSession(SQLiteSession):
    """SQLiteSession whose ``close()`` closes every connection it opened."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._connections: list[sqlite3.Connection] = []
        super().__init__(*args, **kwargs)

    def _get_connection(self) -> sqlite3.Connection:
        opening = not self._is_memory_db and not hasattr(self._local, 'connection')
        connection = super()._get_connection()
        if opening:
            with self._lock:
                self._connections.append(connection)
        return connection

    def close(self) -> None:
        with self._lock:
            connections, self._connections = self._connections, []
        for connection in connections:
            connection.close()
        super().close()


# The sessions opened while a task runs; set by ``closing_sessions`` for the
# duration of the task (a ContextVar, so concurrent tasks on the same loop each
# see their own list) and None outside one, where callers close by hand.
_open_sessions: ContextVar[list[TrackedSQLiteSession] | None] = ContextVar(
    'open_agent_sessions', default=None
)


def _open(session_id: str) -> TrackedSQLiteSession:
    # Mirrors lib.api.db.get_engine's mkdir: sqlite_dir usually already exists
    # by the time a handler runs, but nothing guarantees it, and SQLiteSession
    # fails outright rather than creating a missing parent.
    Path(env.sqlite_dir).mkdir(parents=True, exist_ok=True)
    session = TrackedSQLiteSession(
        session_id=session_id, db_path=env.sqlite_dir / AGENT_SESSIONS_DB_NAME
    )
    opened = _open_sessions.get()
    if opened is not None:
        opened.append(session)
    return session


def agent_session(task_id: int) -> TrackedSQLiteSession:
    """The local follow-up history for one task, across all its reruns."""
    return _open(f'task-{task_id}')


def chat_session(paper_id: int) -> TrackedSQLiteSession:
    """The chat conversation history for one paper.

    Same SQLiteSession mechanism and db file as agent_session, keyed with a
    distinct prefix ('chat-' vs 'task-') so the two id spaces never collide.
    """
    return _open(f'chat-{paper_id}')


@contextmanager
def closing_sessions() -> Iterator[None]:
    """Close every session opened inside the block when it ends.

    Wraps a task's handler in the worker, so a handler can open its session
    the natural way and forget it; nesting is fine, each level closes its own.
    """
    token = _open_sessions.set([])
    try:
        yield
    finally:
        opened = _open_sessions.get() or []
        _open_sessions.reset(token)
        for session in opened:
            session.close()


async def clear_task_session(task_id: int) -> None:
    """Drop a task's stored turns (a fresh rerun), leaving nothing open."""
    with closing_sessions():
        await agent_session(task_id).clear_session()
