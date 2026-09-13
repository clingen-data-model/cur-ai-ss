"""Aggregates over historical task runs, used to estimate progress."""

from pydantic import BaseModel

from lib.tasks.models import TaskType


class TaskDurationStat(BaseModel):
    """How long one kind of task has historically taken."""

    type: TaskType
    median_seconds: float
    samples: int

    # p90 alongside the median because the two together say how predictable a
    # task type is. A type whose p90 is close to its median estimates well; one
    # where they diverge is a coin flip, and a UI can say "about 4 minutes"
    # versus "4-20 minutes" rather than implying a precision it does not have.
    p90_seconds: float


class TaskStatsResp(BaseModel):
    """Per-type run times, plus a fallback for types never yet observed.

    Deliberately not a per-paper estimate: what a given paper still owes depends
    on which of its tasks are outstanding, which the caller already knows from
    its task list. This supplies the per-type costs to price that with.
    """

    task_durations: list[TaskDurationStat]

    # The bars' denominators, and the grouping they draw. Served together so the
    # frontend does not keep its own copy of which task type belongs to which
    # track -- two copies would drift into a silently mis-scaled bar.
    tracks: list['TrackDurationStat'] = []

    # The pipeline's leaves. A caller cannot tell "this level finished" from
    # "the whole run finished" by looking at a task list: right after Pedigree
    # Description lands, every task the paper has is Completed, and the rest do
    # not exist yet. A run is done when each of these has completed.
    terminal_task_types: list[TaskType] = []

    # Used for a task type with no history -- a newly added agent, or one that
    # has never run here. Better than treating it as free, which would make a
    # progress bar jump to completion and then stall.
    overall_median_seconds: float | None = None

    # How many runs the whole thing rests on. A caller showing time estimates
    # can check this before implying any precision.
    total_samples: int


class TrackDurationStat(BaseModel):
    """How long one track has historically taken end to end.

    Wall clock -- the last finish minus the first start across a paper's tasks
    of that track -- not the sum of their durations. Tasks within a track run
    concurrently, so summing would overstate it badly.

    This is what the progress bars divide by, and the reason they cannot run
    backwards: the denominator is a constant from history rather than a count
    of rows that currently exist, so discovering or deleting tasks cannot move
    it. The numerator is elapsed time, which only increases.
    """

    id: str
    label: str
    task_types: list[TaskType]
    median_seconds: float | None = None
    p90_seconds: float | None = None
    # Papers this was measured over. None of the above is trustworthy at 1.
    papers: int = 0
