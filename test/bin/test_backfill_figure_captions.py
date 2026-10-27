"""lib.bin.backfill_figure_captions copies each old row's caption from the
anchored text on disk, the same text a re-run of Figure Description reads."""

import pytest

from lib.bin.backfill_figure_captions import backfill, backfill_paper
from lib.misc.pdf.anchors import Anchor, write_anchored
from lib.models import GeneDB, PaperDB
from lib.models.figure import FigureDescriptionDB


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
    write_anchored(
        paper.id,
        '[figure-0] ![Figure 1. The family](x/0.png)\n\n'
        '[paragraph-1] text\n\n'
        '[figure-2] ![](x/2.png)\n',
        [Anchor(id='figure-0'), Anchor(id='paragraph-1'), Anchor(id='figure-2')],
    )
    write_anchored(
        paper.id,
        '[supp-figure-0] ![Figure S1. Traces](x/0.png)\n',
        [Anchor(id='supp-figure-0')],
        supplement=True,
    )


def test_fills_captionless_rows_from_both_sections(db_session, paper):
    """Main and supplement rows each get the alt text of their own figure
    line; a figure whose line has no alt text stays None, as a re-run would
    leave it."""
    _write_documents(paper)
    db_session.add_all([_row(paper, 0), _row(paper, 2), _row(paper, 0, True)])
    db_session.flush()

    assert backfill_paper(db_session, paper.id) == 2

    rows = db_session.query(FigureDescriptionDB).order_by(
        FigureDescriptionDB.is_supplement, FigureDescriptionDB.image_id
    )
    assert [(r.is_supplement, r.image_id, r.caption) for r in rows] == [
        (False, 0, 'Figure 1. The family'),
        (False, 2, None),
        (True, 0, 'Figure S1. Traces'),
    ]


def test_a_row_that_has_a_caption_is_left_alone(db_session, paper):
    """Re-runnable: a caption the step stored itself is not overwritten from
    disk, and a paper with nothing to fill does not read its files at all."""
    db_session.add(_row(paper, 0, caption='kept'))
    db_session.flush()

    assert backfill_paper(db_session, paper.id) == 0  # no anchored text on disk
    assert db_session.query(FigureDescriptionDB).one().caption == 'kept'


def test_a_paper_without_anchored_text_raises(db_session, paper):
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

    backfill()
    db_session.expire_all()

    captions = {
        (r.paper_id, r.image_id): r.caption
        for r in db_session.query(FigureDescriptionDB)
    }
    assert captions == {(paper.id, 0): 'Figure 1. The family', (other.id, 0): None}
