"""Agent sessions release every sqlite connection they open.

The SDK's file-backed SQLiteSession opens one connection per thread and does
its work on executor threads, while its own close() only covers the calling
thread. These tests open connections from other threads the way the SDK does
and check they are closed by our close() and by closing_sessions(); the
worker leaked ~2 descriptors per task run until it hit its limit (2026-09-30).
"""

import asyncio
import sqlite3

import pytest

from lib.tasks import agent_session
from lib.tasks.agent_session import (
    TrackedSQLiteSession,
    chat_session,
    clear_task_session,
    closing_sessions,
)
from lib.tasks.agent_session import (
    agent_session as open_agent_session,
)


@pytest.fixture
def sessions_dir(tmp_path, monkeypatch):
    # sqlite_dir is a property derived from CAA_ROOT; point it at a scratch dir.
    monkeypatch.setattr(
        type(agent_session.env), 'sqlite_dir', property(lambda _: tmp_path / 'sqllite')
    )
    return tmp_path / 'sqllite'


def _is_closed(connection: sqlite3.Connection) -> bool:
    try:
        connection.execute('select 1')
    except sqlite3.ProgrammingError:
        return True
    return False


async def test_close_covers_connections_opened_on_other_threads(sessions_dir):
    session = open_agent_session(7)
    await session.add_items([{'role': 'user', 'content': 'hi'}])  # to_thread
    await asyncio.to_thread(session.get_items)  # a second executor thread, maybe
    session._get_connection()  # and one on the loop thread itself

    opened = list(session._connections)
    assert opened and all(not _is_closed(c) for c in opened)

    session.close()

    assert all(_is_closed(c) for c in opened)
    assert session._connections == []


async def test_closing_sessions_closes_what_the_block_opened(sessions_dir):
    with closing_sessions():
        task_session = open_agent_session(1)
        paper_session = chat_session(2)
        await task_session.add_items([{'role': 'user', 'content': 'a'}])
        await paper_session.add_items([{'role': 'user', 'content': 'b'}])
        opened = task_session._connections + paper_session._connections
        assert opened

    assert all(_is_closed(c) for c in opened)


async def test_closing_sessions_closes_on_the_way_out_of_an_error(sessions_dir):
    with pytest.raises(RuntimeError), closing_sessions():
        session = open_agent_session(3)
        await session.add_items([{'role': 'user', 'content': 'a'}])
        opened = list(session._connections)
        raise RuntimeError('handler failed')

    assert opened and all(_is_closed(c) for c in opened)


async def test_concurrent_tasks_close_only_their_own_sessions(sessions_dir):
    """The registry is a ContextVar: two tasks on one loop do not see each other."""
    started = asyncio.Event()
    release = asyncio.Event()
    long_lived: list[TrackedSQLiteSession] = []

    async def slow_task():
        with closing_sessions():
            session = open_agent_session(10)
            await session.add_items([{'role': 'user', 'content': 'slow'}])
            long_lived.append(session)
            started.set()
            await release.wait()

    async def quick_task():
        await started.wait()
        with closing_sessions():
            session = open_agent_session(11)
            await session.add_items([{'role': 'user', 'content': 'quick'}])

    slow = asyncio.create_task(slow_task())
    await quick_task()
    assert all(not _is_closed(c) for c in long_lived[0]._connections)
    release.set()
    await slow
    assert long_lived[0]._connections == []


async def test_clear_task_session_leaves_nothing_open(sessions_dir):
    with closing_sessions():
        session = open_agent_session(5)
        await session.add_items([{'role': 'user', 'content': 'old turn'}])

    await clear_task_session(5)

    with closing_sessions():
        assert await open_agent_session(5).get_items() == []


async def test_outside_a_block_sessions_are_closed_by_hand(sessions_dir):
    session = open_agent_session(9)
    await session.add_items([{'role': 'user', 'content': 'x'}])
    assert agent_session._open_sessions.get() is None
    session.close()
    assert session._connections == []
