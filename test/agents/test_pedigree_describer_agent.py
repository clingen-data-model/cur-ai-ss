from lib.agents import pedigree_describer_agent as pedigree
from lib.agents.pedigree_describer_agent import NOT_A_PEDIGREE


def test_usable_description_is_returned(monkeypatch):
    monkeypatch.setattr(pedigree, 'vlm_describe', lambda *_: 'III-2 affected male')

    assert pedigree._analyze_image_url('data:image/png;base64,AAA') == (
        'III-2 affected male'
    )


def test_no_usable_answer_reads_as_not_a_pedigree(monkeypatch):
    """Truncated and refused answers both land here, so the describer moves to
    the next figure instead of recording half an analysis as authoritative."""
    monkeypatch.setattr(pedigree, 'vlm_describe', lambda *_: None)

    assert pedigree._analyze_image_url('data:image/png;base64,AAA') == NOT_A_PEDIGREE


def test_a_declined_figure_is_never_captured(monkeypatch):
    """NOT_A_PEDIGREE is what keeps PedigreeCapture empty, which is what the
    caller stores as the paper's pedigree analysis."""
    monkeypatch.setattr(pedigree, 'vlm_describe', lambda *_: None)
    capture = pedigree.PedigreeCapture()

    description = pedigree._analyze_image_url('data:image/png;base64,AAA')
    if description.strip() != NOT_A_PEDIGREE:
        capture.record(1, description)

    assert capture.image_id is None
    assert capture.description is None
