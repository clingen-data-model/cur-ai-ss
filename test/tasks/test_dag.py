"""Invariants the task graph has to keep, whatever the tasks themselves do.

Extraction moved from ten task types to one, and these are the properties that
made that a safe swap rather than a rewrite of the queue: the graph still
declares every edge it walks, and the worker can still find a handler for
anything it dequeues.
"""

from lib.tasks.handlers import TASK_HANDLERS
from lib.tasks.misc import get_all_successor_levels
from lib.tasks.models import TASK_SUCCESSORS, TaskType

# Answering a question about a paper is triggered from the UI and never
# enqueued as pipeline work, so it is the one type with no place in the graph.
NOT_PIPELINE = {TaskType.GENERAL_PAPER_QUESTION}


def test_every_pipeline_type_declares_its_successors():
    """enqueue_successors raises on a type it has no case for; this catches the
    same omission at import time instead of mid-run."""
    assert set(TASK_SUCCESSORS) == set(TaskType) - NOT_PIPELINE


def test_every_type_the_worker_can_dequeue_has_a_handler():
    assert set(TASK_HANDLERS) == set(TaskType) - NOT_PIPELINE


def test_every_successor_is_reachable_from_parsing():
    """Parsing is the only entry point, so anything it cannot reach is dead."""
    reachable = {TaskType.PDF_PARSING}
    for level in get_all_successor_levels(TaskType.PDF_PARSING):
        reachable.update(level)
    assert reachable == set(TaskType) - NOT_PIPELINE


def test_the_graph_is_acyclic():
    """A cycle would have the worker re-enqueueing forever."""
    seen: set[TaskType] = set()

    def walk(task: TaskType, path: tuple[TaskType, ...]) -> None:
        assert task not in path, f'cycle: {" -> ".join(t.name for t in path + (task,))}'
        seen.add(task)
        for successor in TASK_SUCCESSORS.get(task, []):
            walk(successor, path + (task,))

    walk(TaskType.PDF_PARSING, ())
    assert seen == set(TaskType) - NOT_PIPELINE


def test_each_reading_pass_feeds_the_lookups_that_need_it():
    """The tool-backed tasks were kept out of the reading passes because they
    need a lookup. Each now hangs off the pass that produces what it reads, so
    nothing waits on an entity it does not use."""
    assert TASK_SUCCESSORS[TaskType.PATIENT_DETAILS] == [TaskType.HPO_LINKING]
    assert TASK_SUCCESSORS[TaskType.PATIENT_GENOTYPES] == [TaskType.MONDO_LINKING]
    assert TASK_SUCCESSORS[TaskType.SEGREGATION_EVIDENCE] == [
        TaskType.SEGREGATION_ANALYSIS_COMPUTED
    ]
    # Harmonization needs only the variants, which structure produces.
    assert TaskType.VARIANT_HARMONIZATION in TASK_SUCCESSORS[TaskType.PAPER_STRUCTURE]
    # Annotation needs harmonized coordinates, so it hangs off harmonization.
    assert TASK_SUCCESSORS[TaskType.VARIANT_HARMONIZATION] == [
        TaskType.VARIANT_ANNOTATION
    ]


def test_the_reading_passes_run_in_a_chain_then_a_fork():
    """Structure is the only fork: the passes after it need it and nothing
    else, so the worker runs all three at once."""
    assert TASK_SUCCESSORS[TaskType.PDF_PARSING] == [
        TaskType.PEDIGREE_IDENTIFICATION,
        TaskType.PAPER_METADATA,
    ]
    assert TASK_SUCCESSORS[TaskType.PEDIGREE_IDENTIFICATION] == [
        TaskType.PAPER_STRUCTURE
    ]
    reading_passes = {
        TaskType.PATIENT_DETAILS,
        TaskType.PATIENT_GENOTYPES,
        TaskType.SEGREGATION_EVIDENCE,
    }
    assert reading_passes < set(TASK_SUCCESSORS[TaskType.PAPER_STRUCTURE])
    for pass_type in reading_passes:
        predecessors = [t for t, succ in TASK_SUCCESSORS.items() if pass_type in succ]
        assert predecessors == [TaskType.PAPER_STRUCTURE]
