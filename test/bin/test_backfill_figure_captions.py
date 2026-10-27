"""lib.bin.backfill_figure_captions copies each old row's caption from the
anchored text on disk, the same text a re-run of Figure Description reads."""

import pytest

from lib.agents.figure_describer import Legend
from lib.bin import backfill_figure_captions as script
from lib.bin.backfill_figure_captions import backfill, backfill_paper
from lib.misc.pdf.anchors import Anchor, write_anchored
from lib.misc.pdf.paths import (
    document_anchored_md_path,
    document_anchors_path,
    document_image_path,
)
from lib.models import GeneDB, PaperDB
from lib.models.figure import CaptionSource, FigureDescriptionDB


@pytest.fixture
def paper(db_session):
    gene = GeneDB(symbol='MSX1')
    db_session.add(gene)
    db_session.flush()
    paper = PaperDB(content_hash='abc123', gene_id=gene.id, filename='msx1.pdf')
    db_session.add(paper)
    db_session.flush()
    return paper


def _row(paper, image_id, supplement=False, caption=None):
    return FigureDescriptionDB(
        paper_id=paper.id,
        image_id=image_id,
        is_supplement=supplement,
        kinds=['Pedigree'],
        caption=caption,
        description='d',
    )


def _write_documents(paper):
    """Main text: an attached caption (figure-0), an orphan legend heading
    under figure-2 (which the parser would adopt today, but this document
    predates that), and figure-3 with only prose beside it; a supplement
    whose one caption anchors.json marks as adopted. Image files for every
    figure, since the describer lists only figures that have one."""
    write_anchored(
        paper.id,
        '[figure-0] ![Figure 1. The family](x/0.png)\n\n'
        '[paragraph-1] text\n\n'
        '[figure-2] ![](x/2.png)\n\n'
        '## Figure 2. Traces of the proband\n\n'
        '[figure-3] ![](x/3.png)\n\n'
        '[paragraph-4] Figure 3 shows nothing here.\n',
        [
            Anchor(id='figure-0'),
            Anchor(id='paragraph-1'),
            Anchor(id='figure-2'),
            Anchor(id='figure-3'),
            Anchor(id='paragraph-4'),
        ],
    )
    write_anchored(
        paper.id,
        '[supp-figure-0] ![Figure S1. Traces](x/0.png)\n',
        [Anchor(id='supp-figure-0', caption_adopted=True)],
        supplement=True,
    )
    for image_id, supplement in ((0, False), (2, False), (3, False), (0, True)):
        path = document_image_path(paper.id, image_id, supplement=supplement)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'png')


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    """The model is asked only where a test says so."""
    monkeypatch.setattr(script, 'find_legend', lambda *_: pytest.fail('asked'))


def test_fills_captionless_rows_from_both_sections(db_session, paper):
    """Main and supplement rows each get the alt text of their own figure
    line with its source; a figure whose line has none stays None without
    the model, whatever is printed beside it (figure-2's heading is the
    model's to pick). The anchored text is not rewritten."""
    _write_documents(paper)
    db_session.add_all(
        [_row(paper, 0), _row(paper, 2), _row(paper, 3), _row(paper, 0, True)]
    )
    db_session.flush()

    assert backfill_paper(db_session, paper.id, ask_model=False) == 2

    rows = db_session.query(FigureDescriptionDB).order_by(
        FigureDescriptionDB.is_supplement, FigureDescriptionDB.image_id
    )
    assert [
        (r.is_supplement, r.image_id, r.caption, r.caption_source) for r in rows
    ] == [
        (False, 0, 'Figure 1. The family', CaptionSource.DOCLING),
        (False, 2, None, None),
        (False, 3, None, None),
        (True, 0, 'Figure S1. Traces', CaptionSource.ADJACENT),  # adopted at parse
    ]
    assert (
        '## Figure 2. Traces of the proband'
        in document_anchored_md_path(paper.id).read_text()
    )


def test_a_row_that_has_a_caption_is_left_alone(db_session, paper):
    """Re-runnable: a caption the step stored itself is not overwritten from
    disk, and a paper with nothing to fill does not read its files at all."""
    db_session.add(_row(paper, 0, caption='kept'))
    db_session.flush()

    assert backfill_paper(db_session, paper.id) == 0  # no anchored text on disk
    assert db_session.query(FigureDescriptionDB).one().caption == 'kept'


def test_a_paper_without_anchored_text_fills_nothing(db_session, paper):
    db_session.add(_row(paper, 0))
    db_session.flush()

    assert backfill_paper(db_session, paper.id) == 0


def test_a_paper_whose_anchors_file_is_missing_raises(db_session, paper):
    """The entry point catches this per paper and counts it as skipped."""
    _write_documents(paper)
    document_anchors_path(paper.id).unlink()
    db_session.add(_row(paper, 0))
    db_session.flush()

    with pytest.raises(OSError):
        backfill_paper(db_session, paper.id)


def test_backfill_walks_every_paper_and_skips_the_unreadable(db_session, paper):
    """The entry point commits per paper, so a paper whose files are gone
    costs nothing but a log line while the others are filled."""
    other = PaperDB(content_hash='def456', gene_id=paper.gene_id, filename='o.pdf')
    db_session.add(other)
    db_session.flush()
    _write_documents(paper)
    db_session.add_all([_row(paper, 0), _row(other, 0)])
    db_session.commit()

    backfill(ask_model=False)
    db_session.expire_all()

    captions = {
        (r.paper_id, r.image_id): r.caption
        for r in db_session.query(FigureDescriptionDB)
    }
    assert captions == {(paper.id, 0): 'Figure 1. The family', (other.id, 0): None}


def test_a_figure_the_text_gives_no_legend_for_is_asked_of_the_model(
    monkeypatch, db_session, paper
):
    """figure-3's line carries no caption, so the model is shown its image
    and the prose around it, the way the describer does; its answer is
    stored. figure-0, whose line carries one, is not asked. A row whose
    image is gone (figure-7) is not asked either: the describer would not
    visit it."""
    _write_documents(paper)
    db_session.add_all([_row(paper, 0), _row(paper, 3), _row(paper, 7)])
    db_session.flush()
    asked: list = []

    def fake_find_legend(image_url, nearby, notes):
        asked.append((image_url, nearby, notes))
        return Legend(
            'Figure 3. The model read this off the image',
            CaptionSource.MODEL_TRANSCRIBED,
        )

    monkeypatch.setattr(script, 'find_legend', fake_find_legend)
    monkeypatch.setattr(script, 'image_to_data_url', lambda path: f'data:{path.name}')

    assert backfill_paper(db_session, paper.id) == 2

    assert asked == [
        (
            'data:3.png',
            (
                ('paragraph-1', 'text'),
                ('heading', 'Figure 2. Traces of the proband'),
                ('paragraph-4', 'Figure 3 shows nothing here.'),
            ),
            None,
        )
    ]
    captions = {
        r.image_id: (r.caption, r.caption_source)
        for r in db_session.query(FigureDescriptionDB)
    }
    assert captions == {
        0: ('Figure 1. The family', CaptionSource.DOCLING),
        3: (
            'Figure 3. The model read this off the image',
            CaptionSource.MODEL_TRANSCRIBED,
        ),
        7: (None, None),
    }
