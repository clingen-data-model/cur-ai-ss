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
Docling's own choice.

The whole-figure box is a weak detection, and the post-processor drops any
picture under a confidence of 0.5 before it groups anything, so the box has
to clear that bar for the rule above to matter. It clears it by a hair or
not at all: paper 113's Figure 1 box came in at 0.52 from one PDF
renderer's page image and 0.48 from another's on 2026-11-02 (the pypdfium2
and docling-parse backends on docling 2.142.1), and at 0.48 the figure
split into its five panels. So the second half of the override runs before
the bar: a picture below it that contains two or more pictures above it,
and is contained by none, is a box around a whole figure and is lifted to
the bar (``promote_whole_figures``). One contained picture is just a
duplicate detection, which stays below the bar as Docling meant.

The layout options expose no switch for either, so the group selection and
the post-processor's constructor are replaced on the class; docling is
pinned (pyproject) and the replacements are checked by test_layout.py
against that version's signatures.
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


# The confidence a picture needs to survive the post-processor's first cut.
PICTURE_BAR = LayoutPostprocessor.CONFIDENCE_THRESHOLDS[DocItemLabel.PICTURE]


def whole_figure_boxes(clusters: list[Cluster]) -> list[Cluster]:
    """The pictures below the bar that are a box around two or more pictures
    above it (containing each, contained by none): the whole-figure detections
    the bar would otherwise drop."""
    pictures = [c for c in clusters if c.label == DocItemLabel.PICTURE]
    confident = [c for c in pictures if c.confidence >= PICTURE_BAR]
    found = []
    for candidate in pictures:
        if candidate.confidence >= PICTURE_BAR or any(
            candidate.bbox.intersection_over_self(c.bbox) > CONTAINMENT
            for c in confident
        ):
            continue
        panels = [
            p
            for p in confident
            if p.bbox.intersection_over_self(candidate.bbox) > CONTAINMENT
        ]
        if len(panels) >= 2:
            found.append(candidate)
    return found


def promote_whole_figures(clusters: list[Cluster]) -> None:
    """Lift every whole-figure box to the bar, in place."""
    for cluster in whole_figure_boxes(clusters):
        cluster.confidence = PICTURE_BAR


_init_docling = LayoutPostprocessor.__init__


def _init_promoting_whole_figures(
    self: LayoutPostprocessor, *args: Any, **kwargs: Any
) -> None:
    _init_docling(self, *args, **kwargs)
    # The constructor has split the clusters by type; the picture cut is
    # taken from ``special_clusters`` when the pictures are processed.
    promote_whole_figures(self.special_clusters)


def install() -> None:
    """Replace the group selection and the constructor on Docling's
    post-processor; idempotent."""
    LayoutPostprocessor._select_best_cluster_from_group = _select_keeping_the_container  # type: ignore[method-assign]
    LayoutPostprocessor.__init__ = _init_promoting_whole_figures  # type: ignore[method-assign]


def installed() -> bool:
    return (
        LayoutPostprocessor._select_best_cluster_from_group
        is _select_keeping_the_container
        and LayoutPostprocessor.__init__ is _init_promoting_whole_figures
    )
