"""Returning a stuck task to the queue.

One lease covers every task type, so there is nothing left to test about how
long it is -- what remains is the one thing here that is logic rather than a
constant.
"""

import datetime
from types import SimpleNamespace

from lib.bin.worker import LEASE_TIMEOUT_S, select_timed_out
from lib.tasks.models import TaskType


def test_naive_stored_timestamps_do_not_break_the_reset_check():
    """SQLite returns naive datetimes; the check compares against an aware now.

    Comparing the two directly raises TypeError, which in the poll loop would
    take the worker down rather than reset one task.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    stale_naive = now.replace(tzinfo=None) - datetime.timedelta(
        seconds=LEASE_TIMEOUT_S + 600
    )
    fresh_naive = now.replace(tzinfo=None)

    stale = SimpleNamespace(updated_at=stale_naive, type=TaskType.HPO_LINKING)
    fresh = SimpleNamespace(updated_at=fresh_naive, type=TaskType.HPO_LINKING)

    assert select_timed_out([stale, fresh], now) == [stale]
