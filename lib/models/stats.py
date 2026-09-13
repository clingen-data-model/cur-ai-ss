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

    # Used for a task type with no history -- a newly added agent, or one that
    # has never run here. Better than treating it as free, which would make a
    # progress bar jump to completion and then stall.
    overall_median_seconds: float | None = None

    # How many runs the whole thing rests on. A caller showing time estimates
    # can check this before implying any precision.
    total_samples: int
