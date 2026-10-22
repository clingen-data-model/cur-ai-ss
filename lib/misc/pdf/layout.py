"""Keep a multi-panel figure whole through Docling's layout post-processing.

Docling's layout model predicts a picture box per panel of a figure and often
one more around the whole figure. Its post-processor then groups pictures that
overlap or contain one another (transitively, by union-find) and keeps exactly
one box per group, the highest-scoring: a rule meant for duplicate detections
of the same object, which has no notion of a parent box with children. One
weak box around a whole figure therefore joins every panel into one group and
all but the best panel are discarded, their text cells dumped into it. Paper
116's Figure 1 lost its two pedigrees, two chromatograms and a micrograph that
way on 2026-10-22: six panels detected at 0.53-0.87, a whole-figure box at
0.52, and only the schematic (0.87) survived.

The override below changes which member of a group survives: when one member
contains every other, that container wins. For a figure that is the whole
figure, which is what the vision step wants to see anyway (every panel, read
together under the one caption). A group with no such container, two
detections of one object or boxes that merely overlap, falls back to
Docling's own choice. The layout options expose no switch for this, so the
method is replaced on the class; docling is pinned (pyproject) and the
replacement is checked by test_layout.py against that version's signature.
"""

from typing import Any

from docling.datamodel.base_models import Cluster
from docling.utils.layout_postprocessor import LayoutPostprocessor
from docling_core.types.doc import DocItemLabel

# A member counts as containing another at this share of the other's area,
# the same bar the post-processor itself uses to group them.
CONTAINMENT = 0.8


def container_of(group: list[Cluster]) -> Cluster | None:
    """The one member that contains every other member of the group, if any.

    Containment is one-way: a member that is itself contained by another
    is a duplicate or a child, not a container, so two near-identical boxes
    of one object give None and Docling's rule decides between them."""
    for candidate in group:
        others = [c for c in group if c is not candidate]
        if not others:
            return None
        if all(
            other.bbox.intersection_over_self(candidate.bbox) > CONTAINMENT
            and candidate.bbox.intersection_over_self(other.bbox) <= CONTAINMENT
            for other in others
        ):
            return candidate
    return None


_select_docling = LayoutPostprocessor._select_best_cluster_from_group


def _select_keeping_the_container(
    self: LayoutPostprocessor, group_clusters: list[Cluster], params: dict[str, Any]
) -> Cluster:
    if group_clusters and group_clusters[0].label == DocItemLabel.PICTURE:
        container = container_of(group_clusters)
        if container is not None:
            return container
    return _select_docling(self, group_clusters, params)


def install() -> None:
    """Replace the group selection on Docling's post-processor; idempotent."""
    LayoutPostprocessor._select_best_cluster_from_group = _select_keeping_the_container  # type: ignore[method-assign]


def installed() -> bool:
    return (
        LayoutPostprocessor._select_best_cluster_from_group
        is _select_keeping_the_container
    )
