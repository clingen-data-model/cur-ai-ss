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
    """The pipeline's shape: which task types group into which track.

    Deliberately not a per-paper estimate: what a given paper still owes
    depends on which of its tasks are outstanding and their live status, which
    the caller already knows from its task list -- a row's own status and
    instances are enough to judge it, without needing to know its place in the
    wider DAG. This supplies the track grouping the progress list colours by.
    """

    # The grouping the progress list draws, and its color-coding. Served
    # together so the frontend does not keep its own copy of which task type
    # belongs to which track -- two copies would drift.
    tracks: list['TrackDurationStat'] = []


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
