"""agent_session backs the additional-context rerun feature -- these confirm
the local SQLiteSession is wired up the way lib.tasks.handlers relies on: a
task keeps its history across separate agent_session(task_id) calls (each
handler invocation makes a fresh one), distinct tasks never share history,
and clear_session actually empties it.
"""

import pytest

from lib.core.environment import env
from lib.tasks.agent_session import agent_session


@pytest.fixture(autouse=True)
def _isolated_sqlite_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(env, 'CAA_ROOT', str(tmp_path))


async def test_items_persist_across_separate_agent_session_calls():
    """Each handler invocation constructs its own SQLiteSession; the history
    has to live in the file, not the Python object, for a rerun to see it."""
    await agent_session(42).add_items([{'role': 'user', 'content': 'hello'}])

    items = await agent_session(42).get_items()

    assert items == [{'role': 'user', 'content': 'hello'}]


async def test_distinct_tasks_never_share_history():
    await agent_session(1).add_items([{'role': 'user', 'content': 'task one'}])

    assert await agent_session(2).get_items() == []


async def test_clear_session_empties_stored_history():
    await agent_session(7).add_items([{'role': 'user', 'content': 'before reset'}])

    await agent_session(7).clear_session()

    assert await agent_session(7).get_items() == []
