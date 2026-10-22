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


def test_the_override_is_installed_on_the_pinned_docling():
    # parse.py installs it at import; the class is shared with Docling's own
    # layout stage, so the attribute is the whole mechanism.
    layout.install()
    assert layout.installed()
    # The replaced method still exists upstream with the signature we wrap.
    params = list(inspect.signature(layout._select_docling).parameters)
    assert params == ['self', 'group_clusters', 'params']
    assert (
        LayoutPostprocessor._select_best_cluster_from_group
        is layout._select_keeping_the_container
    )
