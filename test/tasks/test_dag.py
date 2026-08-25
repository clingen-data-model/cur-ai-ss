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
    assert TASK_SUCCESSORS[TaskType.PATIENT_DEMOGRAPHICS] == [TaskType.HPO_LINKING]
    assert TASK_SUCCESSORS[TaskType.PATIENT_VARIANT_OCCURRENCES] == [
        TaskType.MONDO_LINKING
    ]
    assert TASK_SUCCESSORS[TaskType.SEGREGATION_EVIDENCE_EXTRACTION] == [
        TaskType.SEGREGATION_ANALYSIS_COMPUTED
    ]
    # Harmonization needs only the variants.
    assert (
        TaskType.VARIANT_HARMONIZATION in TASK_SUCCESSORS[TaskType.VARIANT_EXTRACTION]
    )
    # Annotation needs harmonized coordinates, so it hangs off harmonization.
    assert TASK_SUCCESSORS[TaskType.VARIANT_HARMONIZATION] == [
        TaskType.VARIANT_ANNOTATION
    ]


def test_the_reading_passes_run_in_a_chain_then_a_fork():
    """Structure is the only fork: the passes after it need it and nothing
    else, so the worker runs all three at once."""
    # Everything that needs only the PDF forks straight off parsing.
    assert TASK_SUCCESSORS[TaskType.PDF_PARSING] == [
        TaskType.PAPER_CLASSIFIER,
        TaskType.PATIENT_EXTRACTION,
        TaskType.VARIANT_EXTRACTION,
        TaskType.PEDIGREE_DESCRIPTION,
        TaskType.PAPER_METADATA,
    ]
    # Two leaves: they write paper-level rows nothing else is keyed to.
    assert TASK_SUCCESSORS[TaskType.PEDIGREE_DESCRIPTION] == []
    assert TASK_SUCCESSORS[TaskType.PAPER_CLASSIFIER] == []

    # Demographics and segregation follow the roster alone.
    for pass_type in (
        TaskType.PATIENT_DEMOGRAPHICS,
        TaskType.SEGREGATION_EVIDENCE_EXTRACTION,
    ):
        predecessors = [t for t, succ in TASK_SUCCESSORS.items() if pass_type in succ]
        assert predecessors == [TaskType.PATIENT_EXTRACTION]


def test_occurrences_wait_on_both_extractions():
    """Linking a patient to a variant needs both, so the task hangs off each and
    enqueue_successors queues it when the second one lands."""
    predecessors = {
        t
        for t, succ in TASK_SUCCESSORS.items()
        if TaskType.PATIENT_VARIANT_OCCURRENCES in succ
    }
    assert predecessors == {TaskType.PATIENT_EXTRACTION, TaskType.VARIANT_EXTRACTION}
