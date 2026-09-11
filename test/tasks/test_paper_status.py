import pytest

from lib.models.paper import PaperTaskStatus
from lib.tasks.misc import summarize_paper_task_status
from lib.tasks.models import TaskStatus

P, Q, R, C, F = (
    TaskStatus.PENDING,
    TaskStatus.QUEUED,
    TaskStatus.RUNNING,
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
)


@pytest.mark.parametrize(
    'statuses,expected',
    [
        ([], PaperTaskStatus.IDLE),
        ([P, P], PaperTaskStatus.PENDING),
        ([R, P], PaperTaskStatus.RUNNING),
        ([Q, P], PaperTaskStatus.RUNNING),
        ([F, P], PaperTaskStatus.FAILED),
        ([C, C], PaperTaskStatus.COMPLETED),
        ([C, P], PaperTaskStatus.PARTIAL),
    ],
)
def test_summarizes_to_the_expected_badge(statuses, expected):
    assert summarize_paper_task_status(statuses) == expected


def test_running_outranks_failed():
    """An active retry must not read as broken while it is still running."""
    assert summarize_paper_task_status([R, F]) == PaperTaskStatus.RUNNING


def test_failed_outranks_completed():
    """One failure is never hidden by its siblings succeeding."""
    assert summarize_paper_task_status([F, C, C]) == PaperTaskStatus.FAILED


def test_idle_is_distinct_from_pending():
    """The two collapse together in tasks.infer_paper_status; the gene table
    draws them as different badges ('Not started' vs 'Pending'), which is why
    this summary exists separately."""
    assert summarize_paper_task_status([]) != summarize_paper_task_status([P])


def test_accepts_any_iterable():
    """Callers pass the result of a two-column query, not a materialised list."""
    assert summarize_paper_task_status(s for s in [C, C]) == PaperTaskStatus.COMPLETED
