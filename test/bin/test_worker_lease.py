"""Per-task-type lease timeouts.

The reading passes run for minutes; the lookup tasks that dominate the queue
run for seconds. One global lease cannot serve both without either abandoning
long tasks mid-flight or leaving stuck short ones parked.

Splitting extraction into passes inverted which way the override points. One
giant task needed *longer* than the default. A single pass is bounded at 480s
with one retry, so it can be given something *shorter* -- a stuck pass comes
back in twenty minutes rather than thirty, and nothing legitimate is cut off.
"""

import datetime
from types import SimpleNamespace

from lib.agents.paper_extraction import _shared
from lib.bin.worker import (
    LEASE_TIMEOUT_OVERRIDES_S,
    LEASE_TIMEOUT_S,
    lease_timeout_for,
    select_timed_out,
)
from lib.tasks.models import TaskType

READING_PASSES = {
    TaskType.PEDIGREE_IDENTIFICATION,
    TaskType.PAPER_STRUCTURE,
    TaskType.PATIENT_DETAILS,
    TaskType.PATIENT_GENOTYPES,
    TaskType.SEGREGATION_EVIDENCE,
}


def test_a_reading_pass_recovers_sooner_than_the_default():
    for task_type in READING_PASSES:
        assert lease_timeout_for(task_type) < LEASE_TIMEOUT_S


def test_the_lease_still_clears_a_pass_that_runs_its_full_course():
    """A pass that times out and retries takes 960s; the lease must exceed that
    or the worker would reset a task that is still legitimately working."""
    worst_case = _shared._ATTEMPT_TIMEOUT_S * (_shared._MAX_RETRIES + 1)
    for task_type in READING_PASSES:
        assert lease_timeout_for(task_type) > worst_case


def test_other_types_keep_the_default():
    for task_type in (TaskType.HPO_LINKING, TaskType.VARIANT_HARMONIZATION):
        assert lease_timeout_for(task_type) == LEASE_TIMEOUT_S


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


def test_a_stuck_pass_is_reset_while_a_lookup_of_the_same_age_is_not():
    """The poll loop filters on the shortest lease and then applies each task's
    own, so the two must not be conflated in either direction."""
    now = datetime.datetime.now(datetime.timezone.utc)
    age = max(LEASE_TIMEOUT_OVERRIDES_S.values()) + 60
    assert age < LEASE_TIMEOUT_S, 'a lookup this old would time out too'
    started = now.replace(tzinfo=None) - datetime.timedelta(seconds=age)

    reading = SimpleNamespace(updated_at=started, type=TaskType.PAPER_STRUCTURE)
    lookup = SimpleNamespace(updated_at=started, type=TaskType.HPO_LINKING)

    assert select_timed_out([reading, lookup], now) == [reading]


def test_only_the_reading_passes_override_the_default():
    assert set(LEASE_TIMEOUT_OVERRIDES_S) == READING_PASSES
