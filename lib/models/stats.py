"""The pipeline's structure, used to derive live progress from a paper's own
task list rather than from a historical time estimate.

A per-track/per-type historical duration used to live here, but a single task
type can now be re-run on its own (see the per-row "re-run this agent" actions
throughout the UI) without disturbing the rest of the pipeline -- there is no
way to group historical spans that a targeted single-task re-run does not
corrupt, so nothing here tries to estimate a duration anymore.
"""

from pydantic import BaseModel

from lib.tasks.models import TaskType


class TaskStatsResp(BaseModel):
    """The pipeline's shape: which task types group into which track, its
    terminal (leaf) task types, and each type's direct predecessor(s).

    Deliberately not a per-paper estimate: what a given paper still owes
    depends on which of its tasks are outstanding and their live status, which
    the caller already knows from its task list. This supplies the pipeline
    structure to interpret that with.
    """

    # The grouping the progress list draws, and its color-coding. Served
    # together so the frontend does not keep its own copy of which task type
    # belongs to which track -- two copies would drift.
    tracks: list['TrackDurationStat'] = []

    # The pipeline's leaves. A caller cannot tell "this level finished" from
    # "the whole run finished" by looking at a task list: right after Pedigree
    # Description lands, every task the paper has is Completed, and the rest do
    # not exist yet. A run is done when each of these has completed.
    terminal_task_types: list[TaskType] = []

    # A type's direct predecessor(s) in the pipeline DAG (PREDECESSOR_TASK_TYPES,
    # the reverse of TASK_SUCCESSORS). Lets a caller tell whether a fan-out
    # type's current rows are the complete set or might still grow: once every
    # predecessor instance is Completed, nothing more of this type can be
    # created, so its own rows are safe to treat as final.
    predecessor_task_types: dict[TaskType, list[TaskType]] = {}


class TrackDurationStat(BaseModel):
    """One of the pipeline's tracks -- which task types belong to it, and
    where it sits in the pipeline's ordering.

    id/label/task_types/stage only: no timing data (see module docstring).
    """

    id: str
    label: str
    task_types: list[TaskType]
    # Pipeline ordering; see PIPELINE_TRACKS. Tracks sharing a stage overlap, a
    # later stage waits on an earlier one.
    stage: int
