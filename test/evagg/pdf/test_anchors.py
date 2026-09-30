import json

import fitz
import pytest
from docling_core.types.doc import (
    BoundingBox,
    ContentLayer,
    CoordOrigin,
    DocItemLabel,
    DoclingDocument,
    GroupLabel,
    ProvenanceItem,
    Size,
    TableCell,
    TableData,
)

from lib.misc.pdf.anchors import (
    Anchor,
    PageBox,
    _display_to_user,
    _PageFrame,
    anchored_from_markdown,
    block_texts,
    boxes_for_anchor,
    build_anchored,
    load_anchors,
    page_frames,
    parse_anchor,
    user_to_display,
    write_anchored,
)
from lib.misc.pdf.paths import (
    UNRECOVERED_TABLE_MARKER,
    document_image_path,
    document_raw_path,
    document_table_unrecovered_path,
    document_table_vision_markdown_path,
)

PAGE_HEIGHT = 800.0


def _bottom_left(l: float, t: float, r: float, b: float) -> ProvenanceItem:
    return ProvenanceItem(
        page_no=1,
        bbox=BoundingBox(l=l, t=t, r=r, b=b, coord_origin=CoordOrigin.BOTTOMLEFT),
        charspan=(0, 1),
    )


def _top_left_cell(l: float, t: float, r: float, b: float) -> BoundingBox:
    return BoundingBox(l=l, t=t, r=r, b=b, coord_origin=CoordOrigin.TOPLEFT)


def _document() -> DoclingDocument:
    """Heading, paragraph, captioned 2x2 table with a grid, captioned figure, list."""
    doc = DoclingDocument(name='test')
    doc.add_page(page_no=1, size=Size(width=600, height=PAGE_HEIGHT))
    doc.add_heading('Results', level=1, prov=_bottom_left(10, 790, 200, 770))
    doc.add_text(
        label=DocItemLabel.TEXT,
        text='Hello world',
        prov=_bottom_left(10, 700, 200, 680),
    )

    cells = []
    for row in range(3):
        for col in range(2):
            cells.append(
                TableCell(
                    text=f'r{row}c{col}',
                    start_row_offset_idx=row,
                    end_row_offset_idx=row + 1,
                    start_col_offset_idx=col,
                    end_col_offset_idx=col + 1,
                    bbox=_top_left_cell(
                        10 + col * 100, 300 + row * 20, 100 + col * 100, 320 + row * 20
                    ),
                    column_header=row == 0,
                )
            )
    caption = doc.add_text(label=DocItemLabel.CAPTION, text='Table 1. Stuff')
    doc.add_table(
        data=TableData(num_rows=3, num_cols=2, table_cells=cells),
        caption=caption,
        prov=_bottom_left(10, 500, 300, 440),
    )

    figure_caption = doc.add_text(label=DocItemLabel.CAPTION, text='Figure 1. Pedigree')
    doc.add_picture(caption=figure_caption, prov=_bottom_left(10, 400, 300, 340))

    group = doc.add_list_group()
    doc.add_list_item('first', parent=group, prov=_bottom_left(10, 200, 300, 190))
    doc.add_list_item('second', parent=group, prov=_bottom_left(10, 190, 300, 180))
    return doc


@pytest.fixture
def paper_id(mocked_root_dir):
    return 1


def test_build_anchored_text_and_ids(paper_id):
    md, anchors = build_anchored(_document(), paper_id=paper_id)

    assert [a.id for a in anchors] == [
        'paragraph-1',
        'table-0',
        'figure-0',
        'paragraph-4',
        'paragraph-5',
    ]
    lines = md.splitlines()
    assert '## Results' in lines  # headers are printed untagged and get no anchor
    assert '[paragraph-1] Hello world' in lines
    assert '[table-0] Table 1. Stuff' in lines
    assert '| anchor | r0c0   | r0c1   |' in lines
    assert '|---|--------|--------|' in lines
    assert '| table-0-row-0 | r1c0   | r1c1   |' in lines
    assert '| table-0-row-1 | r2c0   | r2c1   |' in lines
    assert '[figure-0] Figure 1. Pedigree' in lines  # no images/0.png on disk
    assert '[paragraph-4] - first' in lines
    assert '[paragraph-5] - second' in lines
    assert 'EXTRACTION WARNING' not in md


def test_build_anchored_boxes(paper_id):
    _, anchors = build_anchored(_document(), paper_id=paper_id)
    by_id = {a.id: a for a in anchors}

    # Boxes are in PDF user space (bottom-left origin, y up). Text prov is
    # already there: x = l, y = b, height = t - b.
    assert by_id['paragraph-1'].boxes == [
        PageBox(page_no=1, x=10, y=680, width=190, height=20)
    ]
    # Table/picture prov is in the displayed frame; with no raw.pdf on disk the
    # page counts as unrotated at the origin, so that is just the y flip too.
    assert by_id['figure-0'].boxes == [
        PageBox(page_no=1, x=10, y=340, width=290, height=60)
    ]
    table = by_id['table-0']
    assert table.boxes == [PageBox(page_no=1, x=10, y=440, width=290, height=60)]
    # Grid cells are TOPLEFT in the displayed frame; rendered row r is grid row
    # r+1, so row 0 is the cells at t=320..340 -> y = 800 - 340 = 460.
    assert table.row_boxes == [
        [PageBox(page_no=1, x=10, y=460, width=190, height=20)],
        [PageBox(page_no=1, x=10, y=440, width=190, height=20)],
    ]


def _write_pdf(paper_id: int, *, width: float, height: float, rotation: int) -> None:
    """A one-page raw.pdf in the paper's document dir, as write_anchored_document leaves it."""
    path = document_raw_path(paper_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = fitz.open()
    pdf.new_page(width=width, height=height).set_rotation(rotation)
    pdf.save(path)


def test_rotated_page_boxes_are_in_user_space(paper_id):
    # Paper 74 page 7 in miniature: a 595x794 page with /Rotate 90, so it is
    # displayed 794 wide and 595 tall and Docling reports size=794x595.
    _write_pdf(paper_id, width=595, height=794, rotation=90)
    doc = DoclingDocument(name='rotated')
    doc.add_page(page_no=1, size=Size(width=794, height=595))
    # Text prov: user space, a tall strip (the row runs up the unrotated page).
    doc.add_text(
        label=DocItemLabel.TEXT,
        text='Any ICD (ICD + CRT-D) 30.1%',
        prov=_bottom_left(333, 693, 364, 64),
    )
    # Table prov: displayed frame, BOTTOMLEFT over the displayed height 595.
    cells = [
        TableCell(
            text=f'r{row}c{col}',
            start_row_offset_idx=row,
            end_row_offset_idx=row + 1,
            start_col_offset_idx=col,
            end_col_offset_idx=col + 1,
            bbox=_top_left_cell(
                60 + col * 300, 180 + row * 20, 360 + col * 300, 200 + row * 20
            ),
            column_header=row == 0,
        )
        for row in range(2)
        for col in range(2)
    ]
    doc.add_table(
        data=TableData(num_rows=2, num_cols=2, table_cells=cells),
        prov=_bottom_left(59, 418, 730, 188),
    )

    _, anchors = build_anchored(doc, paper_id=paper_id)
    by_id = {a.id: a for a in anchors}

    assert by_id['paragraph-0'].boxes == [
        PageBox(page_no=1, x=333, y=64, width=31, height=629)
    ]
    # Displayed TOPLEFT (59, 177, 730, 407); rotation-90 inverse x = Y, y = X.
    table = by_id['table-0']
    assert table.boxes == [PageBox(page_no=1, x=177, y=59, width=230, height=671)]
    # Data row cells: displayed TOPLEFT (60, 200, 660, 220) -> x 200..220, y 60..660.
    assert table.row_boxes == [[PageBox(page_no=1, x=200, y=60, width=20, height=600)]]
    # The text strip lies inside the table box, as it does on the real page.
    text_box, table_box = by_id['paragraph-0'].boxes[0], table.boxes[0]
    assert (
        table_box.x <= text_box.x
        and text_box.x + text_box.width <= table_box.x + table_box.width
    )
    assert (
        table_box.y <= text_box.y
        and text_box.y + text_box.height <= table_box.y + table_box.height
    )


def _viewport_forward(x: float, y: float, frame: _PageFrame) -> tuple[float, float]:
    """pdf.js's user-space -> displayed mapping, as written in the section comment."""
    if frame.rotation == 90:
        return y - frame.y0, x - frame.x0
    if frame.rotation == 180:
        return frame.x1 - x, y - frame.y0
    if frame.rotation == 270:
        return frame.y1 - y, frame.x1 - x
    return x - frame.x0, frame.y1 - y


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_display_to_user_inverts_the_viewport_mapping(rotation):
    # An offset visible box (paper 96 style) on every rotation: a user-space
    # rectangle mapped forward to the display and back must come out unchanged.
    frame = _PageFrame(rotation, 34.0, 44.0, 621.0, 826.0)
    l, b, r, t = 100.0, 300.0, 250.0, 380.0
    (x_a, y_a), (x_b, y_b) = (
        _viewport_forward(l, b, frame),
        _viewport_forward(r, t, frame),
    )
    displayed = BoundingBox(
        l=min(x_a, x_b),
        t=min(y_a, y_b),
        r=max(x_a, x_b),
        b=max(y_a, y_b),
        coord_origin=CoordOrigin.TOPLEFT,
    )

    assert _display_to_user(displayed, frame, page_height=0) == (l, b, r, t)


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_user_to_display_is_the_viewport_mapping(rotation):
    # The highlight endpoint's direction: a user-space box lands where pdf.js
    # would draw its corners, as a top-left-origin (x, y, width, height).
    frame = _PageFrame(rotation, 34.0, 44.0, 621.0, 826.0)
    box = PageBox(page_no=1, x=100.0, y=300.0, width=150.0, height=80.0)
    (x_a, y_a), (x_b, y_b) = (
        _viewport_forward(100.0, 300.0, frame),
        _viewport_forward(250.0, 380.0, frame),
    )

    assert user_to_display(box, {1: frame}) == (
        min(x_a, x_b),
        min(y_a, y_b),
        abs(x_a - x_b),
        abs(y_a - y_b),
    )
    assert user_to_display(box, {}) is None  # no such page: nothing to draw


def test_page_frames_reads_rotation_and_visible_box(paper_id):
    _write_pdf(paper_id, width=595, height=794, rotation=90)

    assert page_frames(document_raw_path(paper_id)) == {
        1: _PageFrame(90, 0.0, 0.0, 595.0, 794.0)
    }
    assert page_frames(document_raw_path(paper_id, supplement=True)) == {}


def test_vision_corrected_table_keeps_row_boxes_when_the_counts_agree(paper_id):
    # The rebuilt table has the grid's two data rows: they are the same rows
    # read top to bottom, so Docling's row rectangles still apply.
    vision = document_table_vision_markdown_path(paper_id, 0)
    vision.parent.mkdir(parents=True)
    vision.write_text('| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n')

    md, anchors = build_anchored(_document(), paper_id=paper_id)

    assert '| table-0-row-1 | 3 | 4 |' in md
    assert 'r1c0' not in md
    assert 'EXTRACTION WARNING' not in md
    table = next(a for a in anchors if a.id == 'table-0')
    assert table.row_boxes == [
        [PageBox(page_no=1, x=10, y=460, width=190, height=20)],
        [PageBox(page_no=1, x=10, y=440, width=190, height=20)],
    ]


def test_vision_corrected_table_with_other_row_count_has_no_row_boxes(paper_id):
    vision = document_table_vision_markdown_path(paper_id, 0)
    vision.parent.mkdir(parents=True)
    vision.write_text('| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |\n')

    md, anchors = build_anchored(_document(), paper_id=paper_id)

    assert '| table-0-row-2 | 5 | 6 |' in md
    table = next(a for a in anchors if a.id == 'table-0')
    assert table.row_boxes == [[], [], []]  # rows known, rectangles not trusted
    assert table.boxes  # the table box itself is still there


def test_unrecovered_table_gets_warning_marker(paper_id):
    marker = document_table_unrecovered_path(paper_id, 0)
    marker.parent.mkdir(parents=True)
    marker.touch()

    md, _ = build_anchored(_document(), paper_id=paper_id)

    assert UNRECOVERED_TABLE_MARKER.format(table_id=0) in md
    assert md.index('[table-0]') < md.index('EXTRACTION WARNING') < md.index('| anchor')


def test_figure_with_image_renders_image_reference(paper_id):
    image = document_image_path(paper_id, 0)
    image.parent.mkdir(parents=True)
    image.write_bytes(b'png')

    md, _ = build_anchored(_document(), paper_id=paper_id)

    assert f'[figure-0] ![Figure 1. Pedigree]({image})' in md.splitlines()


def test_supplement_ids_are_prefixed(paper_id):
    md, anchors = build_anchored(_document(), paper_id=paper_id, supplement=True)

    assert anchors[0].id == 'supp-paragraph-1'
    assert '| supp-table-0-row-0 |' in md


def test_document_without_pages_has_no_boxes(paper_id):
    doc = DoclingDocument(name='docx')
    doc.add_text(label=DocItemLabel.TEXT, text='No layout here')

    md, anchors = build_anchored(doc, paper_id=paper_id)

    assert md == '[paragraph-0] No layout here\n'
    assert anchors == [Anchor(id='paragraph-0')]


def test_write_and_load_round_trip(paper_id):
    md, anchors = build_anchored(_document(), paper_id=paper_id)
    write_anchored(paper_id, md, anchors)
    assert load_anchors(paper_id) == anchors


def test_anchored_from_markdown():
    md, anchors = anchored_from_markdown(
        '# Sheet 1\n\n'
        'Some intro text.\n\n'
        '| A | B |\n|---|---|\n| 1 | 2 |\n\n'
        '![chart](/x/images/0.png)\n'
    )

    assert md == (
        '# Sheet 1\n\n'
        '[supp-paragraph-0] Some intro text.\n\n'
        '[supp-table-0]\n\n| anchor | A | B |\n|---|---|---|\n| supp-table-0-row-0 | 1 | 2 |\n\n'
        '[supp-figure-0] ![chart](/x/images/0.png)\n'
    )
    assert anchors == [
        Anchor(id='supp-paragraph-0'),
        Anchor(id='supp-table-0', row_boxes=[[]]),
        Anchor(id='supp-figure-0'),
    ]


@pytest.mark.parametrize(
    'anchor_id, expected',
    [
        ('paragraph-12', (False, 'paragraph', 12, None)),
        ('table-1', (False, 'table', 1, None)),
        ('table-1-row-7', (False, 'table', 1, 7)),
        ('figure-0', (False, 'figure', 0, None)),
        ('supp-table-1-row-7', (True, 'table', 1, 7)),
        ('supp-figure-3', (True, 'figure', 3, None)),
    ],
)
def test_parse_anchor_accepts_grammar(anchor_id, expected):
    parsed = parse_anchor(anchor_id)
    assert parsed is not None
    assert (parsed.supplement, parsed.kind, parsed.index, parsed.row) == expected


@pytest.mark.parametrize(
    'anchor_id',
    ['t1.r3', 'paragraph-', 'row-3', 'paragraph-1-row-2', 'Table-1', ' table-1', ''],
)
def test_parse_anchor_rejects_malformed(anchor_id):
    assert parse_anchor(anchor_id) is None


def test_boxes_for_anchor():
    table_box = PageBox(page_no=1, x=0, y=0, width=10, height=10)
    row_box = PageBox(page_no=1, x=0, y=5, width=10, height=1)
    anchors = [
        Anchor(id='paragraph-3', boxes=[table_box]),
        Anchor(id='table-1', boxes=[table_box], row_boxes=[[row_box], []]),
    ]

    assert boxes_for_anchor('paragraph-3', anchors) == [table_box]
    assert boxes_for_anchor('table-1', anchors) == [table_box]
    assert boxes_for_anchor('table-1-row-0', anchors) == [row_box]
    assert boxes_for_anchor('table-1-row-1', anchors) == [table_box]  # untrusted row
    assert boxes_for_anchor('table-1-row-2', anchors) == []  # no such row
    assert boxes_for_anchor('figure-9', anchors) == []
    assert boxes_for_anchor('nonsense', anchors) == []


def test_inline_group_is_one_paragraph_with_every_items_boxes(paper_id):
    doc = DoclingDocument(name='inline')
    doc.add_page(page_no=1, size=Size(width=600, height=PAGE_HEIGHT))
    group = doc.add_inline_group()
    doc.add_text(
        label=DocItemLabel.TEXT,
        text='inline a',
        parent=group,
        prov=_bottom_left(10, 700, 100, 680),
    )
    doc.add_text(
        label=DocItemLabel.TEXT,
        text='inline b',
        parent=group,
        prov=_bottom_left(100, 700, 200, 680),
    )

    md, anchors = build_anchored(doc, paper_id=paper_id)

    assert md == '[paragraph-0] inline a inline b\n'
    assert [a.id for a in anchors] == ['paragraph-0']
    assert [b.x for b in anchors[0].boxes] == [10, 100]


def test_key_value_group_tags_each_child(paper_id):
    # The serializer folds a key-value area into one blank-line-separated part;
    # 58 such parts in prod ('Received: ...' / 'Accepted: ...' blocks).
    doc = DoclingDocument(name='kv')
    doc.add_page(page_no=1, size=Size(width=600, height=PAGE_HEIGHT))
    group = doc.add_group(label=GroupLabel.KEY_VALUE_AREA, name='group')
    doc.add_text(
        label=DocItemLabel.TEXT,
        text='Received: 6 May 2021',
        parent=group,
        prov=_bottom_left(10, 700, 100, 680),
    )
    doc.add_text(
        label=DocItemLabel.TEXT,
        text='Accepted: 7 June 2021',
        parent=group,
        prov=_bottom_left(10, 680, 100, 660),
    )

    md, anchors = build_anchored(doc, paper_id=paper_id)

    assert (
        md
        == '[paragraph-0] Received: 6 May 2021\n\n[paragraph-1] Accepted: 7 June 2021\n'
    )
    assert [(a.id, a.boxes[0].y) for a in anchors] == [
        ('paragraph-0', 680),
        ('paragraph-1', 660),
    ]


def test_carriage_return_in_cell_does_not_cut_the_row(paper_id):
    # Docling's markdown export maps '\n' in a cell to a space but leaves '\r'.
    doc = DoclingDocument(name='cr')
    doc.add_page(page_no=1, size=Size(width=600, height=PAGE_HEIGHT))
    rows = [['Measure', 'Value'], ['Age (years)\r\n55.6 ± 1.9', '55.6'], ['Sex', 'F']]
    cells = [
        TableCell(
            text=text,
            start_row_offset_idx=r,
            end_row_offset_idx=r + 1,
            start_col_offset_idx=c,
            end_col_offset_idx=c + 1,
            column_header=r == 0,
        )
        for r, row in enumerate(rows)
        for c, text in enumerate(row)
    ]
    doc.add_table(data=TableData(num_rows=3, num_cols=2, table_cells=cells))

    md, anchors = build_anchored(doc, paper_id=paper_id)

    row_lines = [line for line in md.splitlines() if line.startswith('| table-0-row-')]
    assert len(row_lines) == 2
    assert row_lines[0].startswith('| table-0-row-0 | Age (years)')
    assert '55.6 ± 1.9' in row_lines[0]
    assert row_lines[0].count('|') == 4
    assert len(anchors[0].row_boxes) == 2


def test_other_text_kinds_become_paragraphs_and_furniture_is_dropped(paper_id):
    doc = DoclingDocument(name='misc')
    doc.add_page(page_no=1, size=Size(width=600, height=PAGE_HEIGHT))
    doc.add_title('A title')
    doc.add_text(
        label=DocItemLabel.PAGE_HEADER,
        text='running head',
        content_layer=ContentLayer.FURNITURE,
    )
    doc.add_text(label=DocItemLabel.FOOTNOTE, text='a footnote')
    doc.add_code(text='x = 1')
    doc.add_formula(text='E=mc^2')

    md, anchors = build_anchored(doc, paper_id=paper_id)

    assert (
        md
        == (
            '# A title\n\n'
            '[paragraph-2] a footnote\n\n'
            '[paragraph-3]\n```\nx = 1\n```\n\n'  # tag on its own line keeps the fence valid
            '[paragraph-4] $$E=mc^2$$\n'
        )
    )
    assert 'running head' not in md
    assert [a.id for a in anchors] == ['paragraph-2', 'paragraph-3', 'paragraph-4']


def test_zero_area_prov_boxes_are_dropped(paper_id):
    doc = DoclingDocument(name='degenerate')
    doc.add_page(page_no=1, size=Size(width=600, height=PAGE_HEIGHT))
    item = doc.add_text(
        label=DocItemLabel.TEXT, text='wrapped', prov=_bottom_left(10, 700, 200, 680)
    )
    # Docling artefacts seen in prod: a zero-width and a zero-height fragment.
    item.prov.append(_bottom_left(292, 357, 292, 350))
    item.prov.append(_bottom_left(292, 357, 400, 357))

    _, anchors = build_anchored(doc, paper_id=paper_id)

    assert anchors[0].boxes == [PageBox(page_no=1, x=10, y=680, width=190, height=20)]


def test_blank_items_produce_neither_text_nor_anchor(paper_id):
    doc = DoclingDocument(name='blank')
    doc.add_page(page_no=1, size=Size(width=600, height=PAGE_HEIGHT))
    doc.add_formula(text='')  # Docling emits these for unrecognised equation regions
    doc.add_text(label=DocItemLabel.TEXT, text='   ')
    doc.add_text(label=DocItemLabel.TEXT, text='real')

    md, anchors = build_anchored(doc, paper_id=paper_id)

    assert md == '[paragraph-2] real\n'
    assert [a.id for a in anchors] == ['paragraph-2']


# --- block_texts: reading an anchored document back ---------------------------


def test_block_texts_over_a_built_document(paper_id):
    md, anchors = build_anchored(_document(), paper_id=paper_id)

    texts = block_texts(md)

    assert texts['paragraph-1'] == 'Hello world'
    assert texts['table-0'] == (
        'Table 1. Stuff\n| r0c0   | r0c1   |\n| r1c0   | r1c1   |\n| r2c0   | r2c1   |'
    )
    assert texts['table-0-row-0'] == '| r1c0   | r1c1   |'
    assert texts['table-0-row-1'] == '| r2c0   | r2c1   |'
    assert texts['figure-0'] == 'Figure 1. Pedigree'
    assert texts['paragraph-4'] == '- first'
    assert texts['paragraph-5'] == '- second'
    # Every anchor has a text, every row id too, and headings have none.
    assert set(texts) == {a.id for a in anchors} | {'table-0-row-0', 'table-0-row-1'}
    assert not any('Results' in text for text in texts.values())


def test_block_texts_skips_the_unrecovered_marker(paper_id):
    marker = document_table_unrecovered_path(paper_id, 0)
    marker.parent.mkdir(parents=True)
    marker.touch()
    md, _ = build_anchored(_document(), paper_id=paper_id)

    texts = block_texts(md)

    assert 'EXTRACTION WARNING' not in texts['table-0']
    assert texts['table-0'].startswith('Table 1. Stuff\n| r0c0')


def test_block_texts_uses_image_alt_text(paper_id):
    image = document_image_path(paper_id, 0)
    image.parent.mkdir(parents=True)
    image.write_bytes(b'png')
    md, _ = build_anchored(_document(), paper_id=paper_id)

    assert block_texts(md)['figure-0'] == 'Figure 1. Pedigree'


def test_block_texts_over_plain_markdown_output():
    md, _ = anchored_from_markdown(
        '# Sheet 1\n\nSome intro text.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n'
        '![chart](/x/images/0.png)\n'
    )

    assert block_texts(md) == {
        'supp-paragraph-0': 'Some intro text.',
        'supp-table-0': '| A | B |\n| 1 | 2 |',  # no caption
        'supp-table-0-row-0': '| 1 | 2 |',
        'supp-figure-0': 'chart',
    }


def test_block_texts_hand_written_layouts():
    md = (
        '## Heading\n\n'
        '[paragraph-3]\n```\nline one\n\nline three\n```\n\n'
        '[paragraph-4] First line\nsecond line\n\n'
        '[figure-1] ![Fig. 1 | legend](/x/images/1.png)\n\n'
        '[table-2] Caption\n\n'
        '| anchor | A | B |\n|---|---|---|\n'
        '| table-2-row-0 | a<br>b | c \r d |\n'
        'Trailing note, not a row\n\n'
        '[1] a bracketed reference, not a tag\n'
    )

    texts = block_texts(md)

    assert texts['paragraph-3'] == '```\nline one\n\nline three\n```'
    assert texts['paragraph-4'] == 'First line\nsecond line'
    assert texts['figure-1'] == 'Fig. 1 | legend'
    assert texts['table-2'] == 'Caption\n| A | B |\n| a<br>b | c \r d |'
    assert texts['table-2-row-0'] == '| a<br>b | c \r d |'
    assert '[1]' not in ''.join(texts)
    assert set(texts) == {
        'paragraph-3',
        'paragraph-4',
        'figure-1',
        'table-2',
        'table-2-row-0',
    }
