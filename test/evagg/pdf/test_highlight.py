import json

import fitz
import pytest

from lib.misc.pdf import highlight
from lib.misc.pdf.anchors import Anchor, PageBox, _PageFrame, write_anchored
from lib.misc.pdf.highlight import (
    GrobidAnnotation,
    citations_to_grobid_annotations,
    find_best_match,
    word_frame_to_user,
    words_within,
)
from lib.misc.pdf.parse import WordLoc
from lib.misc.pdf.paths import document_raw_path, document_words_json_path
from lib.models.evidence_block import Citation


def test_find_best_match_across_page_break():
    """Test find_best_match with a 10-15 word query across a page break in a 30-word PDF."""
    # Simulate a 30-word PDF split across 2 pages
    words = [
        # Page 1: 16 words
        WordLoc(
            word='The', page_idx=1, x0=0, y0=0, x1=10, y1=10, x2=10, y2=10, x3=0, y3=0
        ),
        WordLoc(
            word='study',
            page_idx=1,
            x0=20,
            y0=0,
            x1=30,
            y1=10,
            x2=30,
            y2=10,
            x3=20,
            y3=0,
        ),
        WordLoc(
            word='examined',
            page_idx=1,
            x0=40,
            y0=0,
            x1=50,
            y1=10,
            x2=50,
            y2=10,
            x3=40,
            y3=0,
        ),
        WordLoc(
            word='genetic',
            page_idx=1,
            x0=60,
            y0=0,
            x1=70,
            y1=10,
            x2=70,
            y2=10,
            x3=60,
            y3=0,
        ),
        WordLoc(
            word='mutations',
            page_idx=1,
            x0=80,
            y0=0,
            x1=90,
            y1=10,
            x2=90,
            y2=10,
            x3=80,
            y3=0,
        ),
        WordLoc(
            word='in',
            page_idx=1,
            x0=100,
            y0=0,
            x1=110,
            y1=10,
            x2=110,
            y2=10,
            x3=100,
            y3=0,
        ),
        WordLoc(
            word='patient',
            page_idx=1,
            x0=120,
            y0=0,
            x1=130,
            y1=10,
            x2=130,
            y2=10,
            x3=120,
            y3=0,
        ),
        WordLoc(
            word='samples',
            page_idx=1,
            x0=140,
            y0=0,
            x1=150,
            y1=10,
            x2=150,
            y2=10,
            x3=140,
            y3=0,
        ),
        WordLoc(
            word='from',
            page_idx=1,
            x0=160,
            y0=0,
            x1=170,
            y1=10,
            x2=170,
            y2=10,
            x3=160,
            y3=0,
        ),
        WordLoc(
            word='different',
            page_idx=1,
            x0=180,
            y0=0,
            x1=190,
            y1=10,
            x2=190,
            y2=10,
            x3=180,
            y3=0,
        ),
        WordLoc(
            word='geographic',
            page_idx=1,
            x0=200,
            y0=0,
            x1=210,
            y1=10,
            x2=210,
            y2=10,
            x3=200,
            y3=0,
        ),
        WordLoc(
            word='regions',
            page_idx=1,
            x0=220,
            y0=0,
            x1=230,
            y1=10,
            x2=230,
            y2=10,
            x3=220,
            y3=0,
        ),
        WordLoc(
            word='using',
            page_idx=1,
            x0=240,
            y0=0,
            x1=250,
            y1=10,
            x2=250,
            y2=10,
            x3=240,
            y3=0,
        ),
        WordLoc(
            word='advanced',
            page_idx=1,
            x0=260,
            y0=0,
            x1=270,
            y1=10,
            x2=270,
            y2=10,
            x3=260,
            y3=0,
        ),
        WordLoc(
            word='sequencing',
            page_idx=1,
            x0=280,
            y0=0,
            x1=290,
            y1=10,
            x2=290,
            y2=10,
            x3=280,
            y3=0,
        ),
        WordLoc(
            word='technologies',
            page_idx=1,
            x0=300,
            y0=0,
            x1=310,
            y1=10,
            x2=310,
            y2=10,
            x3=300,
            y3=0,
        ),
        # Page 2: 14 words (page break)
        WordLoc(
            word='to', page_idx=2, x0=0, y0=0, x1=10, y1=10, x2=10, y2=10, x3=0, y3=0
        ),
        WordLoc(
            word='identify',
            page_idx=2,
            x0=20,
            y0=0,
            x1=30,
            y1=10,
            x2=30,
            y2=10,
            x3=20,
            y3=0,
        ),
        WordLoc(
            word='novel',
            page_idx=2,
            x0=40,
            y0=0,
            x1=50,
            y1=10,
            x2=50,
            y2=10,
            x3=40,
            y3=0,
        ),
        WordLoc(
            word='pathogenic',
            page_idx=2,
            x0=60,
            y0=0,
            x1=70,
            y1=10,
            x2=70,
            y2=10,
            x3=60,
            y3=0,
        ),
        WordLoc(
            word='variants',
            page_idx=2,
            x0=80,
            y0=0,
            x1=90,
            y1=10,
            x2=90,
            y2=10,
            x3=80,
            y3=0,
        ),
        WordLoc(
            word='associated',
            page_idx=2,
            x0=100,
            y0=0,
            x1=110,
            y1=10,
            x2=110,
            y2=10,
            x3=100,
            y3=0,
        ),
        WordLoc(
            word='with',
            page_idx=2,
            x0=120,
            y0=0,
            x1=130,
            y1=10,
            x2=130,
            y2=10,
            x3=120,
            y3=0,
        ),
        WordLoc(
            word='rare',
            page_idx=2,
            x0=140,
            y0=0,
            x1=150,
            y1=10,
            x2=150,
            y2=10,
            x3=140,
            y3=0,
        ),
        WordLoc(
            word='diseases',
            page_idx=2,
            x0=160,
            y0=0,
            x1=170,
            y1=10,
            x2=170,
            y2=10,
            x3=160,
            y3=0,
        ),
        WordLoc(
            word='in',
            page_idx=2,
            x0=180,
            y0=0,
            x1=190,
            y1=10,
            x2=190,
            y2=10,
            x3=180,
            y3=0,
        ),
        WordLoc(
            word='clinical',
            page_idx=2,
            x0=200,
            y0=0,
            x1=210,
            y1=10,
            x2=210,
            y2=10,
            x3=200,
            y3=0,
        ),
        WordLoc(
            word='practice',
            page_idx=2,
            x0=220,
            y0=0,
            x1=230,
            y1=10,
            x2=230,
            y2=10,
            x3=220,
            y3=0,
        ),
        WordLoc(
            word='and',
            page_idx=2,
            x0=240,
            y0=0,
            x1=250,
            y1=10,
            x2=250,
            y2=10,
            x3=240,
            y3=0,
        ),
        WordLoc(
            word='research',
            page_idx=2,
            x0=260,
            y0=0,
            x1=270,
            y1=10,
            x2=270,
            y2=10,
            x3=260,
            y3=0,
        ),
    ]

    # Query spans across page break: 15 words
    query = 'sequencing technologies to identify novel'

    result = find_best_match(query, words)

    assert result is not None, 'Should find a match across page break'
    assert len(result) > 0, 'Should return matched words'

    # Verify match spans both pages
    page_indices = [w.page_idx for w in result]
    assert 1 in page_indices, 'Should include words from page 1'
    assert 2 in page_indices, 'Should include words from page 2'

    # Verify key words are present
    result_words = [w.word for w in result]
    assert 'sequencing' in result_words
    assert 'technologies' in result_words
    assert 'identify' in result_words
    assert 'novel' in result_words


# --- highlighting by citation --------------------------------------------------


def _word(
    text: str, x0: float, y0: float, x1: float, y1: float, page: int = 1
) -> WordLoc:
    """A word box in user space; corners in docling-parse's order (BL, BR, TR, TL)."""
    return WordLoc(
        word=text, page_idx=page, x0=x0, y0=y0, x1=x1, y1=y0, x2=x1, y2=y1, x3=x0, y3=y1
    )


PARAGRAPH = PageBox(page_no=1, x=10, y=680, width=190, height=20)
WORDS = [
    _word('Hello', 10, 682, 40, 698),
    _word('world', 50, 682, 80, 698),
    _word('Elsewhere', 10, 100, 60, 116),  # same page, outside the paragraph
    _word('world', 50, 682, 80, 698, page=2),  # right place, wrong page
    _word('Gene', 10, 462, 40, 478),  # inside table-1's first row (paper_documents)
    _word('cell', 50, 462, 80, 478),
    _word('Case', 10, 322, 40, 338),  # inside figure-0's legend (paper_documents)
    _word('17DG0679', 50, 322, 110, 338),
]


def test_words_within_keeps_the_words_inside_the_boxes_in_order():
    assert [w.word for w in words_within([PARAGRAPH], WORDS)] == ['Hello', 'world']
    # A word sitting on the box edge still counts (the box is grown by tol).
    edge = _word('edge', 199, 682, 205, 698)
    assert words_within([PARAGRAPH], [edge]) == [edge]
    assert words_within([PARAGRAPH], [edge], tol=0) == []
    assert words_within([], WORDS) == []


@pytest.fixture
def paper_documents(mocked_root_dir):
    """anchors.json, words.json and a one-page 600x800 raw.pdf for paper 1."""
    paper_id = 1
    write_anchored(
        paper_id,
        '[paragraph-1] Hello world\n\n[table-1] T\n\n[figure-0] F\n',
        [
            Anchor(id='paragraph-1', boxes=[PARAGRAPH]),
            Anchor(
                id='table-1',
                boxes=[PageBox(page_no=1, x=10, y=440, width=290, height=60)],
                row_boxes=[[PageBox(page_no=1, x=10, y=460, width=190, height=20)], []],
            ),
            Anchor(
                id='figure-0',
                boxes=[PageBox(page_no=1, x=10, y=340, width=290, height=60)],
                caption_boxes=[PageBox(page_no=1, x=10, y=318, width=290, height=20)],
            ),
        ],
    )
    pdf = fitz.open()
    pdf.new_page(width=600, height=800)
    pdf.save(document_raw_path(paper_id))
    document_words_json_path(paper_id).write_text(
        json.dumps([w.model_dump() for w in WORDS])
    )
    return paper_id


RED = (1.0, 0.0, 0.0)


def _placed(annotations: list[GrobidAnnotation]) -> list[tuple[float, ...]]:
    return [(a.page, a.x, a.y, a.width, a.height) for a in annotations]


def test_paragraph_without_a_quote_is_its_whole_box(paper_documents):
    out = citations_to_grobid_annotations(
        paper_documents, [Citation(anchor='paragraph-1')], RED
    )

    # y flips: the box's top edge is at 700 in user space, 100 from the page top.
    assert _placed(out) == [(1, 10.0, 100.0, 190.0, 20.0)]
    assert out[0].color == 'rgb(255.0,0.0,0.0)'


def test_paragraph_with_a_quote_narrows_to_the_quoted_words(paper_documents):
    out = citations_to_grobid_annotations(
        paper_documents, [Citation(anchor='paragraph-1', quote='world')], RED
    )

    assert _placed(out) == [(1, 50.0, 102.0, 30.0, 16.0)]


def test_quote_that_does_not_align_falls_back_to_the_block(
    paper_documents, monkeypatch
):
    monkeypatch.setattr(highlight, 'find_best_match', lambda query, words: None)

    out = citations_to_grobid_annotations(
        paper_documents, [Citation(anchor='paragraph-1', quote='nothing like it')], RED
    )

    assert _placed(out) == [(1, 10.0, 100.0, 190.0, 20.0)]


def test_rows_tables_and_figures_are_their_stored_boxes(paper_documents):
    out = citations_to_grobid_annotations(
        paper_documents,
        [
            Citation(anchor='table-1-row-0'),  # trusted row: its own box
            Citation(anchor='table-1-row-1'),  # untrusted row: the table's
            Citation(
                anchor='table-1', quote='cell'
            ),  # a table cited whole never narrows
            Citation(anchor='figure-0'),
        ],
        RED,
    )

    assert _placed(out) == [
        (1, 10.0, 320.0, 190.0, 20.0),
        (1, 10.0, 300.0, 290.0, 60.0),
        (1, 10.0, 300.0, 290.0, 60.0),
        (1, 10.0, 400.0, 290.0, 60.0),
    ]


def test_figure_with_a_legend_quote_narrows_to_the_legend_words(paper_documents):
    out = citations_to_grobid_annotations(
        paper_documents, [Citation(anchor='figure-0', quote='17DG0679')], RED
    )

    assert _placed(out) == [(1, 50.0, 462.0, 60.0, 16.0)]


def test_figure_quote_not_in_the_legend_stays_the_picture(paper_documents, monkeypatch):
    monkeypatch.setattr(highlight, 'find_best_match', lambda query, words: None)

    out = citations_to_grobid_annotations(
        paper_documents, [Citation(anchor='figure-0', quote='nothing like it')], RED
    )

    assert _placed(out) == [(1, 10.0, 400.0, 290.0, 60.0)]


def test_table_row_with_a_quote_narrows_to_the_quoted_words(paper_documents):
    """A Docling row can be most of a page (a transposed table read as a few tall
    grid rows), so a row citation narrows like a paragraph: to the quote's words
    inside the row's box, or inside the table's when the row's is not trusted."""
    out = citations_to_grobid_annotations(
        paper_documents,
        [
            Citation(anchor='table-1-row-0', quote='cell'),
            Citation(anchor='table-1-row-1', quote='cell'),
        ],
        RED,
    )

    assert _placed(out) == [(1, 50.0, 322.0, 30.0, 16.0)] * 2


def test_unresolvable_citations_contribute_nothing(paper_documents):
    out = citations_to_grobid_annotations(
        paper_documents,
        [
            Citation(anchor='supp-paragraph-1'),  # no PDF for the supplement
            Citation(anchor='paragraph-7'),  # not in anchors.json
            Citation(anchor='table-1-row-9'),  # no such row
            Citation(anchor='paragraph-1'),  # still resolved, in order
        ],
        RED,
    )

    assert _placed(out) == [(1, 10.0, 100.0, 190.0, 20.0)]


def test_word_frame_to_user_undoes_the_rotation_docling_parse_applied():
    """Paper 87 page 4 (603 x 783, /Rotate 90), the cell "62" of its Table 1:
    words.json has it at x 286..294, y 367..374; PyMuPDF puts the same word at
    user x 229..236, y 286..294. An unrotated page is a passthrough."""
    frame = _PageFrame(90, 0.0, 0.0, 602.986, 782.986)
    assert word_frame_to_user(286.36, 367.53, frame) == pytest.approx(
        (235.46, 286.36), abs=0.01
    )
    assert word_frame_to_user(294.34, 374.07, frame) == pytest.approx(
        (228.92, 294.34), abs=0.01
    )
    assert word_frame_to_user(5.0, 7.0, _PageFrame(0, 0.0, 0.0, 600.0, 800.0)) == (
        5.0,
        7.0,
    )
    # Paper 96 page 4: /Rotate 270 on a mediabox [0 251.76 828 827.76], so the
    # frame is offset and the displayed height is the user-space width. words.json
    # has the word "TABLE" at x 68.6..72.2, y 304.5..325.5; PyMuPDF puts it at
    # user x 304.5..325.5, y 752.9..760.5 (a looser box around the same glyphs).
    frame = _PageFrame(270, 0.0, 251.7594, 828.0, 827.7594)
    assert word_frame_to_user(72.2, 304.5, frame) == pytest.approx(
        (304.5, 755.56), abs=0.01
    )
    assert word_frame_to_user(68.6, 325.5, frame) == pytest.approx(
        (325.5, 759.16), abs=0.01
    )


@pytest.fixture
def rotated_paper(mocked_root_dir):
    """Paper 2: a 600x800 page with /Rotate 90 (displayed 800 wide, 600 tall),
    one table in user space, and words.json as docling-parse writes it for a
    rotated page -- in the displayed orientation, y up, in the displayed size."""
    paper_id = 2
    # Displayed, the table spans X 50..400 and Y 150..300; in user space
    # (rotation-90 inverse x = Y, y = X) that is x 150..300, y 50..400.
    table = PageBox(page_no=1, x=150, y=50, width=150, height=350)
    write_anchored(
        paper_id,
        '[table-0] T\n',
        [Anchor(id='table-0', boxes=[table], row_boxes=[[]])],
    )
    pdf = fitz.open()
    pdf.new_page(width=600, height=800).set_rotation(90)
    pdf.save(document_raw_path(paper_id))
    # "62 y" at displayed X 100..130, Y 200..216 is, y up over the displayed
    # height of 600, x 100..130, y 384..400 in the word frame. "Elsewhere" sits
    # at displayed Y 500, below the table; in user space that is x 500, which the
    # unconverted frames would have read as *inside* the table (y 50..400).
    words = [
        _word('62', 100, 384, 115, 400),
        _word('y', 118, 384, 130, 400),
        _word('Elsewhere', 100, 84, 150, 100),
    ]
    document_words_json_path(paper_id).write_text(
        json.dumps([w.model_dump() for w in words])
    )
    return paper_id


def test_rotated_page_quote_is_narrowed_in_the_words_frame(rotated_paper):
    """The quote is found and merged where docling-parse put it, and the box
    comes out where the viewer shows that cell: displayed X 100..130, Y 200..216,
    not rotated a second time (which put it at X 200, Y 100 as a 16 x 30 sliver)."""
    out = citations_to_grobid_annotations(
        rotated_paper, [Citation(anchor='table-0-row-0', quote='62 y')], RED
    )
    assert _placed(out) == [(1, 100.0, 200.0, 30.0, 16.0)]


def test_rotated_page_search_stays_inside_the_cited_block(rotated_paper):
    """A word outside the table on the displayed page is not a candidate, even
    though its raw coordinates fall inside the table's user-space box."""
    out = citations_to_grobid_annotations(
        rotated_paper, [Citation(anchor='table-0-row-0', quote='Elsewhere')], RED
    )
    # Nothing to narrow to: the whole table, displayed (X 50..400, Y 150..300).
    assert _placed(out) == [(1, 50.0, 150.0, 350.0, 150.0)]


def test_box_off_its_page_contributes_nothing(paper_documents):
    """An anchors.json written before clipped text was left out can still hold
    a paragraph drawn off the page (paper 67's paragraph-185 at y -371). It
    covers nothing a reader can see, so it is skipped like an unknown anchor."""
    write_anchored(
        paper_documents,
        '[paragraph-1] Hello world\n\n[paragraph-9] clipped\n',
        [
            Anchor(id='paragraph-1', boxes=[PARAGRAPH]),
            Anchor(
                id='paragraph-9',
                boxes=[PageBox(page_no=1, x=161, y=-371, width=392, height=9)],
            ),
        ],
    )
    out = citations_to_grobid_annotations(
        paper_documents,
        [
            Citation(anchor='paragraph-9', quote='clipped'),
            Citation(anchor='paragraph-1'),
        ],
        RED,
    )

    assert _placed(out) == [(1, 10.0, 100.0, 190.0, 20.0)]


def test_missing_words_json_means_no_narrowing(paper_documents):
    document_words_json_path(paper_documents).unlink()

    out = citations_to_grobid_annotations(
        paper_documents, [Citation(anchor='paragraph-1', quote='world')], RED
    )

    assert _placed(out) == [(1, 10.0, 100.0, 190.0, 20.0)]
