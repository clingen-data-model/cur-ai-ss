"""The track grouping, and the pipeline ordering an estimate reads off it."""

from lib.tasks.models import TASK_SUCCESSORS, TaskType
from lib.tasks.tracks import PIPELINE_TRACKS, TRACK_OF_TYPE

STAGE_OF_TRACK = {track.id: track.stage for track in PIPELINE_TRACKS}


def test_every_pipeline_task_belongs_to_exactly_one_track():
    """A task in no track is priced at nothing; a task in two is priced twice."""
    covered = [t for track in PIPELINE_TRACKS for t in track.task_types]
    assert len(covered) == len(set(covered))
    missing = set(TaskType) - set(covered)
    assert not missing


def test_stages_agree_with_the_dependency_graph():
    """The ordering is declared, so this is what stops it drifting from the DAG
    it was read off.

    Every edge that crosses tracks must run forwards: a task cannot enable one
    in an earlier stage. Tasks within a stage may depend on each other freely --
    that is what makes them one stage.
    """
    for predecessor, successors in TASK_SUCCESSORS.items():
        before = TRACK_OF_TYPE.get(predecessor)
        if before is None:
            continue
        for successor in successors:
            after = TRACK_OF_TYPE.get(successor)
            if after is None or after == before:
                continue
            assert STAGE_OF_TRACK[before] <= STAGE_OF_TRACK[after], (
                f'{predecessor} (stage {STAGE_OF_TRACK[before]}) enables '
                f'{successor} (stage {STAGE_OF_TRACK[after]}), which runs earlier'
            )


def test_the_fork_is_a_fork():
    """Patients and Variants share a stage because both hang off Paper
    Classifier and neither waits on the other -- the concurrency a
    whole-pipeline estimate has to keep, having added the stages around it."""
    assert STAGE_OF_TRACK['patients'] == STAGE_OF_TRACK['variants']
    assert STAGE_OF_TRACK['paper'] < STAGE_OF_TRACK['patients']
    assert STAGE_OF_TRACK['analysis'] > STAGE_OF_TRACK['variants']


def test_stages_are_contiguous_from_zero():
    """A gap would make the sum-of-stages arithmetic silently skip one."""
    stages = sorted({track.stage for track in PIPELINE_TRACKS})
    assert stages == list(range(len(stages)))
