"""A multi-panel figure survives Docling's picture-overlap resolution whole."""

import inspect

from docling.datamodel.base_models import Cluster
from docling.utils.layout_postprocessor import LayoutPostprocessor
from docling_core.types.doc import BoundingBox, DocItemLabel

from lib.misc.pdf import layout


def _picture(cid: int, l: float, t: float, r: float, b: float, conf: float) -> Cluster:
    return Cluster(
        id=cid,
        label=DocItemLabel.PICTURE,
        bbox=BoundingBox(l=l, t=t, r=r, b=b),
        confidence=conf,
    )


# Paper 116's Figure 1, as the layout model boxed it (points, top-left origin).
WHOLE = _picture(9, 57, 37, 355, 476, 0.52)
PANELS = [
    _picture(1, 56, 392, 297, 477, 0.87),  # F, the schematic
    _picture(2, 59, 137, 191, 212, 0.84),  # B, chromatogram
    _picture(3, 213, 137, 348, 213, 0.82),  # D, chromatogram
    _picture(4, 76, 244, 201, 342, 0.78),  # E, micrograph
    _picture(5, 59, 37, 375, 99, 0.71),  # A and C, the pedigrees
]


def test_the_box_around_every_panel_is_the_container():
    assert layout.container_of([*PANELS, WHOLE]) is WHOLE


def test_a_group_of_separate_panels_has_no_container():
    assert layout.container_of(PANELS) is None


def test_two_detections_of_one_object_have_no_container():
    first = _picture(1, 10, 10, 100, 100, 0.9)
    second = _picture(2, 12, 11, 101, 99, 0.6)
    assert layout.container_of([first, second]) is None


def test_a_nested_pair_keeps_the_outer_box():
    outer = _picture(1, 59, 232, 201, 342, 0.62)
    inner = _picture(2, 76, 244, 201, 342, 0.78)
    assert layout.container_of([inner, outer]) is outer


def test_a_lone_member_is_not_its_own_container():
    assert layout.container_of([WHOLE]) is None


def test_docling_decides_when_there_is_no_container(monkeypatch):
    chosen = PANELS[0]
    calls: list[list[Cluster]] = []

    def docling_choice(self: object, group: list[Cluster], params: dict) -> Cluster:
        calls.append(group)
        return chosen

    monkeypatch.setattr(layout, '_select_docling', docling_choice)

    assert layout._select_keeping_the_container(object(), PANELS, {}) is chosen  # type: ignore[arg-type]
    assert calls == [PANELS]


def test_the_container_wins_without_asking_docling(monkeypatch):
    def never(self: object, group: list[Cluster], params: dict) -> Cluster:
        raise AssertionError('Docling was asked')

    monkeypatch.setattr(layout, '_select_docling', never)

    assert layout._select_keeping_the_container(object(), [*PANELS, WHOLE], {}) is WHOLE  # type: ignore[arg-type]


# The same figure boxed from the other renderer's page image: the whole-figure
# box just under Docling's bar, where it would be cut before grouping.
WEAK_WHOLE = _picture(9, 57, 37, 355, 476, 0.48)


def test_a_weak_box_around_two_or_more_panels_is_a_whole_figure():
    assert layout.whole_figure_boxes([*PANELS, WEAK_WHOLE]) == [WEAK_WHOLE]


def test_a_weak_box_around_one_panel_is_a_duplicate_not_a_figure():
    duplicate = _picture(9, 55, 390, 300, 478, 0.48)  # F again, a touch larger
    assert layout.whole_figure_boxes([*PANELS, duplicate]) == []


def test_a_weak_box_inside_a_confident_one_is_not_a_figure():
    inner = _picture(9, 60, 140, 345, 340, 0.45)  # around B, D and E, inside WHOLE
    assert layout.whole_figure_boxes([*PANELS, WHOLE, inner]) == []


def test_a_box_above_the_bar_needs_no_promotion():
    assert layout.whole_figure_boxes([*PANELS, WHOLE]) == []


def test_promotion_lifts_the_box_to_the_bar_and_touches_nothing_else():
    weak = WEAK_WHOLE.model_copy()
    panels = [p.model_copy() for p in PANELS]
    layout.promote_whole_figures([*panels, weak])
    assert weak.confidence == layout.PICTURE_BAR == 0.5
    assert [p.confidence for p in panels] == [p.confidence for p in PANELS]


def test_the_override_is_installed_on_the_pinned_docling():
    # parse.py installs it at import; the class is shared with Docling's own
    # layout stage, so the attributes are the whole mechanism.
    layout.install()
    assert layout.installed()
    # The replaced methods still exist upstream with the signatures we wrap.
    params = list(inspect.signature(layout._select_docling).parameters)
    assert params == ['self', 'group_clusters', 'params']
    params = list(inspect.signature(layout._init_docling).parameters)
    assert params == ['self', 'page', 'clusters', 'options']
    assert (
        LayoutPostprocessor._select_best_cluster_from_group
        is layout._select_keeping_the_container
    )
    assert LayoutPostprocessor.__init__ is layout._init_promoting_whole_figures
    assert LayoutPostprocessor.CONFIDENCE_THRESHOLDS[DocItemLabel.PICTURE] == 0.5


def test_layout_module_imports_nothing_from_lib():
    """The pdf-parsing service image copies layout.py in alone
    (infrastructure/pdf-parsing/Dockerfile) and installs it from a
    sitecustomize.py, so it has to stand on docling and the standard library."""
    import ast
    import inspect

    from lib.misc.pdf import layout

    tree = ast.parse(inspect.getsource(layout))
    modules = {
        node.module.split('.')[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name.split('.')[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert modules <= {'docling', 'docling_core', 'typing'}, modules
