"""The worker polls every POLL_INTERVAL_S, and sooner once something else has
committed to the database: a watch on SQLite's data_version tells it, so a
task the API enqueues, or the successors a completion enqueues, are picked up
within about a second rather than at the end of the interval."""

import asyncio
import time

import pytest

from lib.api import db
from lib.bin import worker
from lib.models import GeneDB


def _commit_from_another_connection(db_session) -> None:
    db_session.add(GeneDB(symbol='BRCA1'))
    db_session.commit()


def _watch() -> worker.DatabaseWatch:
    return worker.DatabaseWatch(str(db.get_engine().url.database))


def test_watch_reports_a_commit_from_another_connection_once(db_session):
    watch = _watch()
    assert not watch.changed()
    _commit_from_another_connection(db_session)
    assert watch.changed()
    assert not watch.changed()


@pytest.mark.asyncio
async def test_wait_ends_as_soon_as_the_database_changes(db_session, monkeypatch):
    monkeypatch.setattr(worker, 'POLL_INTERVAL_S', 30)
    monkeypatch.setattr(worker, 'CHANGE_CHECK_S', 0.05)
    watch = _watch()

    async def commit_soon() -> None:
        await asyncio.sleep(0.1)
        _commit_from_another_connection(db_session)

    commit = asyncio.ensure_future(commit_soon())
    started = time.monotonic()
    await worker._wait_for_change_or_interval(watch)
    await commit
    assert time.monotonic() - started < 2


@pytest.mark.asyncio
async def test_wait_runs_the_whole_interval_when_nothing_changes(
    db_session, monkeypatch
):
    monkeypatch.setattr(worker, 'POLL_INTERVAL_S', 0.3)
    monkeypatch.setattr(worker, 'CHANGE_CHECK_S', 0.05)
    watch = _watch()
    started = time.monotonic()
    await worker._wait_for_change_or_interval(watch)
    assert time.monotonic() - started >= 0.3
