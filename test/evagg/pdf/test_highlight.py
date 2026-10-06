import json

import fitz
import pytest

from lib.misc.pdf import highlight
from lib.misc.pdf.anchors import Anchor, PageBox, write_anchored
from lib.misc.pdf.highlight import (
    GrobidAnnotation,
    citations_to_grobid_annotations,
    find_best_match,
    words_within,
)
from lib.misc.pdf.paths import document_raw_path, document_words_json_path
from lib.misc.pdf.words import WordLoc
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


def test_missing_words_json_means_no_narrowing(paper_documents):
    document_words_json_path(paper_documents).unlink()

    out = citations_to_grobid_annotations(
        paper_documents, [Citation(anchor='paragraph-1', quote='world')], RED
    )

    assert _placed(out) == [(1, 10.0, 100.0, 190.0, 20.0)]
