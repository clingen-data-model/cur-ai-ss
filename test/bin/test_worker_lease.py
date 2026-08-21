"""Per-task-type lease timeouts.

Single-pass curation runs for minutes; the lookup tasks that dominate the queue
run for seconds. One global lease cannot serve both without either abandoning
long tasks mid-flight or leaving stuck short ones parked.
"""

import datetime

from lib.bin.worker import (
    LEASE_TIMEOUT_OVERRIDES_S,
    LEASE_TIMEOUT_S,
    lease_timeout_for,
    select_timed_out,
)
from lib.tasks.models import TaskType


def test_curation_gets_a_longer_lease_than_the_default():
    assert lease_timeout_for(TaskType.PAPER_EXTRACTION) > LEASE_TIMEOUT_S


def test_other_types_keep_the_default():
    for task_type in (TaskType.HPO_LINKING, TaskType.VARIANT_HARMONIZATION):
        assert lease_timeout_for(task_type) == LEASE_TIMEOUT_S


def test_long_lease_survives_past_the_short_one():
    """A curation still running at 31 minutes must not be reset on the 30 minute lease."""
    elapsed = datetime.timedelta(seconds=LEASE_TIMEOUT_S + 60)
    assert elapsed.total_seconds() > lease_timeout_for(TaskType.HPO_LINKING)
    assert elapsed.total_seconds() < lease_timeout_for(TaskType.PAPER_EXTRACTION)


def test_naive_stored_timestamps_do_not_break_the_reset_check():
    """SQLite returns naive datetimes; the check compares against an aware now.

    Comparing the two directly raises TypeError, which in the poll loop would
    take the worker down rather than reset one task.
    """
    from types import SimpleNamespace

    now = datetime.datetime.now(datetime.timezone.utc)
    stale_naive = now.replace(tzinfo=None) - datetime.timedelta(
        seconds=LEASE_TIMEOUT_S + 600
    )
    fresh_naive = now.replace(tzinfo=None)

    stale = SimpleNamespace(updated_at=stale_naive, type=TaskType.HPO_LINKING)
    fresh = SimpleNamespace(updated_at=fresh_naive, type=TaskType.HPO_LINKING)

    assert select_timed_out([stale, fresh], now) == [stale]


def test_curation_is_not_reset_on_the_short_lease():
    """A curation 31 minutes in is past the default lease but not its own."""
    from types import SimpleNamespace

    now = datetime.datetime.now(datetime.timezone.utc)
    started = now.replace(tzinfo=None) - datetime.timedelta(
        seconds=LEASE_TIMEOUT_S + 60
    )

    curation = SimpleNamespace(updated_at=started, type=TaskType.PAPER_EXTRACTION)
    lookup = SimpleNamespace(updated_at=started, type=TaskType.HPO_LINKING)

    timed_out = select_timed_out([curation, lookup], now)
    assert timed_out == [lookup]


def test_overrides_are_a_superset_of_nothing_unexpected():
    assert set(LEASE_TIMEOUT_OVERRIDES_S) == {TaskType.PAPER_EXTRACTION}
