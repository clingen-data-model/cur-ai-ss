import json

import pytest
from docling_core.types.doc import (
    BoundingBox,
    CoordOrigin,
    DocItemLabel,
    DoclingDocument,
    ProvenanceItem,
    Size,
    TableCell,
    TableData,
)

from lib.misc.pdf.anchors import (
    Anchor,
    PageBox,
    anchored_from_markdown,
    boxes_for_anchor,
    build_anchored,
    load_anchors,
    parse_anchor,
    write_anchored,
)
from lib.misc.pdf.paths import (
    UNRECOVERED_TABLE_MARKER,
    document_image_path,
    document_table_correction_path,
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


def test_build_anchored_boxes(paper_id):
    _, anchors = build_anchored(_document(), paper_id=paper_id)
    by_id = {a.id: a for a in anchors}

    # prov is BOTTOMLEFT: y flips through the page height, height = t - b.
    assert by_id['paragraph-1'].boxes == [
        PageBox(page_no=1, x=10, y=PAGE_HEIGHT - 700, width=190, height=20)
    ]
    assert by_id['figure-0'].boxes == [
        PageBox(page_no=1, x=10, y=PAGE_HEIGHT - 400, width=290, height=60)
    ]
    # Grid cells are already TOPLEFT; rendered row r is grid row r+1.
    table = by_id['table-0']
    assert table.boxes == [PageBox(page_no=1, x=10, y=300, width=290, height=60)]
    assert table.row_boxes == [
        [PageBox(page_no=1, x=10, y=320, width=190, height=20)],
        [PageBox(page_no=1, x=10, y=340, width=190, height=20)],
    ]


def test_vision_corrected_table_uses_vision_text_and_no_row_boxes(paper_id):
    vision = document_table_vision_markdown_path(paper_id, 0)
    vision.parent.mkdir(parents=True)
    vision.write_text('| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |\n')

    md, anchors = build_anchored(_document(), paper_id=paper_id)

    assert '| table-0-row-2 | 5 | 6 |' in md
    assert 'r1c0' not in md
    table = next(a for a in anchors if a.id == 'table-0')
    assert table.row_boxes == [[], [], []]  # rows known, rectangles not trusted
    assert table.boxes  # the table box itself is still there


def test_unrecovered_table_gets_warning_marker(paper_id):
    record = document_table_correction_path(paper_id, 0)
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({'is_corrupted': True, 'corrected': False}))

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
