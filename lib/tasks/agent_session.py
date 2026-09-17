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
"""

from pathlib import Path

from agents.memory import SQLiteSession

from lib.core.environment import env

AGENT_SESSIONS_DB_NAME = 'agent_sessions.db'


def agent_session(task_id: int) -> SQLiteSession:
    """The local follow-up history for one task, across all its reruns."""
    # Mirrors lib.api.db.get_engine's mkdir: sqlite_dir usually already exists
    # by the time a handler runs, but nothing guarantees it, and SQLiteSession
    # fails outright rather than creating a missing parent.
    Path(env.sqlite_dir).mkdir(parents=True, exist_ok=True)
    return SQLiteSession(
        session_id=f'task-{task_id}',
        db_path=env.sqlite_dir / AGENT_SESSIONS_DB_NAME,
    )


def chat_session(paper_id: int) -> SQLiteSession:
    """The chat conversation history for one paper.

    Same SQLiteSession mechanism and db file as agent_session, keyed with a
    distinct prefix ('chat-' vs 'task-') so the two id spaces never collide.
    """
    Path(env.sqlite_dir).mkdir(parents=True, exist_ok=True)
    return SQLiteSession(
        session_id=f'chat-{paper_id}',
        db_path=env.sqlite_dir / AGENT_SESSIONS_DB_NAME,
    )
