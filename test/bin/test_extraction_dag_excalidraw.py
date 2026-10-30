"""The Excalidraw drawing of the pipeline is generated from TASK_SUCCESSORS,
so a graph change without a label, or a regenerated graph not committed, is a
test failure rather than a stale picture for curators."""

from pathlib import Path

from lib.bin.extraction_dag_excalidraw import (
    EDGE_LABELS,
    GRID,
    NODE_NOTES,
    build,
    render,
)
from lib.tasks.models import TASK_SUCCESSORS, TaskType


def test_every_task_and_edge_is_drawn_and_labelled():
    edges = {(src, dst) for src, dsts in TASK_SUCCESSORS.items() for dst in dsts}
    assert set(EDGE_LABELS) == edges
    assert set(NODE_NOTES) == set(TaskType) == set(GRID)
    elements = build()['elements']
    by_type: dict[str, list[dict]] = {}
    for el in elements:
        by_type.setdefault(el['type'], []).append(el)
    node_ids = {el['id'] for el in by_type['rectangle'] if el['id'].startswith('node-')}
    assert len(node_ids) == len(TaskType)
    arrows = by_type['arrow']
    assert len(arrows) == len(edges)
    for arrow in arrows:
        assert arrow['startBinding']['elementId'] in node_ids
        assert arrow['endBinding']['elementId'] in node_ids
        assert arrow['boundElements'][0]['type'] == 'text'
    assert len({el['id'] for el in elements}) == len(elements)
    verification = [
        a
        for a in arrows
        if a['endBinding']['elementId'] == 'node-extraction-verification'
    ]
    assert verification and all(a['strokeStyle'] == 'dashed' for a in verification)


def test_the_committed_drawing_is_current():
    """docs/extraction-dag.excalidraw is what `python -m
    lib.bin.extraction_dag_excalidraw` prints; regenerate it after a change."""
    committed = (
        Path(__file__).resolve().parents[2] / 'docs' / 'extraction-dag.excalidraw'
    )
    assert committed.read_text() == render()
