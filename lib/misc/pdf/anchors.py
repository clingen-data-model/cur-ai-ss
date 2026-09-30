"""Anchor-indexed documents: ``anchored.md`` + ``anchors.json``.

Every paragraph, table, table row and figure in a paper gets a stable id that is
printed into the markdown the extraction agents read (``[paragraph-54] ...``)
and that maps, through ``anchors.json``, to the item's boxes on the PDF page.
Evidence then cites ids instead of quotes that have to be re-found at render
time.

Ids are the item's Docling index (``#/texts/54`` -> ``paragraph-54``,
``#/tables/1`` -> ``table-1``, ``#/pictures/0`` -> ``figure-0``), so the same
number keys the on-disk ``tables/N.*`` and ``images/N.png`` files. Row ids
(``table-1-row-7``) number the rendered data rows, header excluded, and are
printed in an ``anchor`` column so the agent copies rather than counts.
Supplement ids carry a ``supp-`` prefix.

Two artifacts, nothing stored twice: ``anchored.md`` is the only text (what
agents read and what curators will see), ``anchors.json`` is a pure id ->
geometry index. Whether a table was vision-corrected is not recorded here: it
is the existence of ``tables/N.vision.md``; its row rectangles are kept only
when the rebuilt table has the grid's row count, else they are empty.
"""

import json
import re
from pathlib import Path
from typing import NamedTuple

import fitz
from docling_core.transforms.serializer.markdown import (
    MarkdownDocSerializer,
    MarkdownParams,
)
from docling_core.types.doc import (
    BoundingBox,
    DocItem,
    DoclingDocument,
    GroupItem,
    GroupLabel,
    ListItem,
    PictureItem,
    SectionHeaderItem,
    TableItem,
    TextItem,
    TitleItem,
)
from docling_core.types.doc.base import CoordOrigin
from pydantic import BaseModel

from lib.misc.pdf.anchor_ids import (
    ANCHOR_RE,
    SUPPLEMENT_PREFIX,
    AnchorKind,
    ParsedAnchor,
    parse_anchor,
)
from lib.misc.pdf.paths import (
    UNRECOVERED_TABLE_MARKER,
    document_anchored_md_path,
    document_anchors_path,
    document_image_path,
    document_raw_path,
    document_table_unrecovered_path,
    document_table_vision_markdown_path,
)

__all__ = [  # the id grammar lives in anchor_ids.py; re-exported here unchanged
    'ANCHOR_RE',
    'SUPPLEMENT_PREFIX',
    'Anchor',
    'AnchorKind',
    'PageBox',
    'ParsedAnchor',
    'anchored_from_markdown',
    'block_texts',
    'boxes_for_anchor',
    'build_anchored',
    'load_anchors',
    'make_anchor_id',
    'page_frames',
    'paper_block_texts',
    'parse_anchor',
    'user_to_display',
    'write_anchored',
]

_PIPE_LINE = re.compile(r'^\s*\|')
_SEPARATOR_LINE = re.compile(r'^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$')
_IMAGE_LINE = re.compile(r'^!\[.*\]\(.*\)\s*$')
_HEADING_LINE = re.compile(r'^#{1,6}\s')


class PageBox(BaseModel):
    """A rectangle on a PDF page, in *PDF user space*: points, origin bottom-left, y up.

    User space is the PDF's own coordinate system -- the numbers in the page's
    content stream, the frame ``words.json`` is in, and the input pdf.js's
    ``viewport.convertToViewportPoint`` expects. Page rotation and cropping are
    deliberately NOT applied here: the viewer applies them when it draws, the
    same way it already places its own text items (see ``PdfViewer.tsx``).
    ``(x, y)`` is the bottom-left corner. See "Page geometry" below for how
    Docling's mixed frames are brought into this one.
    """

    page_no: int
    x: float
    y: float
    width: float
    height: float


class Anchor(BaseModel):
    """One entry of anchors.json: an id and where it is on the PDF pages."""

    id: str
    boxes: list[PageBox] = []  # empty for DOCX/XLSX documents, which have no pages
    # Tables only: one entry per rendered data row, so the row ids are known
    # from this file alone. A row's list is empty when its rectangle cannot be
    # trusted (the Docling grid does not have one row per rendered row, which
    # is common for vision-corrected tables); resolve it to the table's own
    # boxes instead.
    row_boxes: list[list[PageBox]] = []


def boxes_for_anchor(anchor_id: str, anchors: list[Anchor]) -> list[PageBox]:
    """Resolve an id to page boxes; a row without its own boxes gets the table's."""
    parsed = parse_anchor(anchor_id)
    if parsed is None:
        return []
    item_id = anchor_id.rsplit('-row-', 1)[0] if parsed.row is not None else anchor_id
    anchor = next((a for a in anchors if a.id == item_id), None)
    if anchor is None:
        return []
    if parsed.row is None:
        return anchor.boxes
    if parsed.row >= len(anchor.row_boxes):
        return []
    return anchor.row_boxes[parsed.row] or anchor.boxes


def write_anchored(
    paper_id: int, md: str, anchors: list[Anchor], supplement: bool = False
) -> None:
    """Write anchored.md and anchors.json into the paper's document dir."""
    md_path = document_anchored_md_path(paper_id, supplement)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md)
    document_anchors_path(paper_id, supplement).write_text(
        json.dumps([a.model_dump() for a in anchors], indent=1)
    )


def load_anchors(paper_id: int, supplement: bool = False) -> list[Anchor]:
    """Read anchors.json back (the highlight endpoint's lookup table)."""
    path = document_anchors_path(paper_id, supplement)
    return [Anchor.model_validate(a) for a in json.loads(path.read_text())]


# --- building from a DoclingDocument ------------------------------------------


def _docling_index(item: DocItem) -> int:
    """The N in the item's self_ref ('#/tables/3' -> 3): the number every id and file uses."""
    return int(item.self_ref.rsplit('/', 1)[1])


def make_anchor_id(kind: AnchorKind, index: int, supplement: bool) -> str:
    """Format an id: (TABLE, 3, True) -> 'supp-table-3'."""
    prefix = SUPPLEMENT_PREFIX if supplement else ''
    return f'{prefix}{kind}-{index}'


# --- page geometry ---------------------------------------------------------------
#
# Three coordinate frames meet here, and the whole job of this section is to get
# everything into the first one.
#
# 1. PDF user space. The PDF's own coordinates: points, origin at the bottom-left,
#    y up. Every drawing operator in the page's content stream uses it. So does
#    ``words.json`` (docling-parse reads the content stream), and so does pdf.js:
#    ``viewport.convertToViewportPoint(x, y)`` takes user-space input. This is
#    the frame ``PageBox`` is in. Nothing about rotation or cropping lives here.
#
# 2. The displayed page. A page can carry ``/Rotate 90`` ("turn me before you show
#    me") and a cropbox ("only this part of user space is the page"). A viewer
#    applies both and shows an upright page whose top-left corner is (0, 0) and
#    whose y runs down. pdf.js calls this the viewport (at scale 1), and its
#    forward mapping from user space, with ``(x0, y0, x1, y1)`` the visible box
#    (cropbox clipped to the mediabox -- pdf.js's ``viewBox``), is
#
#        rotation   0:  X = x - x0     Y = y1 - y
#        rotation  90:  X = y - y0     Y = x - x0
#        rotation 180:  X = x1 - x     Y = y - y0
#        rotation 270:  X = y1 - y     Y = x1 - x
#
#    On an ordinary page (rotation 0, box at the origin) this is just the y flip,
#    which is why the difference never showed up until the rotated papers did.
#
# 3. What Docling reports. Docling is not in one frame:
#      - TEXT items come from the PDF's text layer, so their ``prov`` boxes are in
#        user space (1), as BOTTOMLEFT boxes.
#      - TABLE and PICTURE items come from a layout model run on the *rendered*
#        page image, so their ``prov`` boxes and a table's grid cells are in the
#        displayed frame (2): cells as TOPLEFT boxes, prov as BOTTOMLEFT boxes
#        measured over the displayed page height, and ``doc.pages[n].size`` is
#        the displayed (rotated) size.
#    Measured, not assumed: a census of the 9 prod papers with rotated pages
#    (2026-09-30) found 880 text boxes that fit only the user-space frame and
#    all 20 table + 2 picture boxes fitting only the displayed frame.
#
# So: text boxes pass through untouched; table, picture and cell boxes go through
# ``_display_to_user``, the inverse of the mapping above, which needs each page's
# rotation and visible box. Those are read from ``raw.pdf`` by ``_page_frames``.
#
# Worked example, paper 74 page 7 (mediabox 595 x 794, /Rotate 90, so displayed
# 794 wide x 595 tall and Docling says size=794x595):
#
#     text  #/texts/369 "Any ICD (ICD + CRT-D) 30.1% ..."   a table row
#           prov BOTTOMLEFT l=333 b=64 r=364 t=693         user space already:
#           -> PageBox(x=333, y=64, w=31, h=629)            a tall thin strip, because
#                                                           the row runs *up* the
#                                                           unrotated page
#     table #/tables/1
#           prov BOTTOMLEFT l=59 b=188 r=730 t=418          displayed frame, height 595
#           -> TOPLEFT      L=59 T=177 R=730 B=407          (T = 595 - 418, B = 595 - 188)
#           -> rotation 90 inverse: x = Y + x0, y = X + y0
#              corners (59, 177) -> (177, 59) and (730, 407) -> (407, 730)
#           -> PageBox(x=177, y=59, w=230, h=671)
#
# and the text strip (x 333..364, y 64..693) now lies inside the table box
# (x 177..407, y 59..730), as it must. Before this conversion the two disagreed
# by hundreds of points, and the table box fell off the page.


class _PageFrame(NamedTuple):
    """One page's ``/Rotate`` and visible box, in user space: what the viewer uses."""

    rotation: int  # 0, 90, 180 or 270, clockwise
    x0: float  # visible box = cropbox clipped to mediabox, raw PDF coordinates
    y0: float
    x1: float
    y1: float


def _page_frames(pdf_path: Path) -> dict[int, _PageFrame]:
    """Read every page's rotation and visible box from the PDF; {} without a PDF.

    fitz reports ``page.mediabox`` in raw PDF coordinates but ``page.cropbox``
    with y measured *down from the mediabox top*, so the cropbox is converted
    back to raw coordinates here (checked: raw /CropBox [150 300 900 800] under
    /MediaBox [100 252 928 828] comes out of fitz as (150, 28, 900, 528)).
    """
    if pdf_path.suffix.lower() != '.pdf' or not pdf_path.exists():
        return {}  # DOCX/XLSX documents have no pages, and no boxes either
    frames = {}
    with fitz.open(pdf_path) as pdf:
        for page in pdf:
            media, crop = page.mediabox, page.cropbox
            raw_crop = fitz.Rect(
                crop.x0, media.y1 - crop.y1, crop.x1, media.y1 - crop.y0
            )
            visible = raw_crop & media  # pdf.js: cropbox intersected with mediabox
            if visible.is_empty:
                visible = media
            frames[page.number + 1] = _PageFrame(
                page.rotation, visible.x0, visible.y0, visible.x1, visible.y1
            )
    return frames


def page_frames(pdf_path: Path) -> dict[int, _PageFrame]:
    """The per-page frames of a PDF, keyed by 1-based page number (see above)."""
    return _page_frames(pdf_path)


def _frame_for(
    frames: dict[int, _PageFrame], page_no: int, width: float, height: float
) -> _PageFrame:
    """The page's frame, or -- with no PDF to read -- an unrotated page at the origin."""
    return frames.get(page_no, _PageFrame(0, 0.0, 0.0, width, height))


def user_to_display(
    box: PageBox, frames: dict[int, _PageFrame]
) -> tuple[float, float, float, float] | None:
    """A ``PageBox`` -> ``(x, y, width, height)`` on the displayed page, or None.

    The forward mapping of the section comment above (what pdf.js draws in:
    top-left origin, y down, rotation and visible box applied), for the
    highlight endpoint, whose viewer positions boxes on the displayed page.
    Both corners are mapped and re-sorted, as ``_display_to_user`` does. None
    when the PDF has no such page, which only happens for a stale anchors.json.
    """
    frame = frames.get(box.page_no)
    if frame is None:
        return None
    corners = [(box.x, box.y), (box.x + box.width, box.y + box.height)]
    if frame.rotation == 90:
        points = [(y - frame.y0, x - frame.x0) for x, y in corners]
    elif frame.rotation == 180:
        points = [(frame.x1 - x, y - frame.y0) for x, y in corners]
    elif frame.rotation == 270:
        points = [(frame.y1 - y, frame.x1 - x) for x, y in corners]
    else:
        points = [(x - frame.x0, frame.y1 - y) for x, y in corners]
    xs, ys = zip(*points, strict=True)
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def _display_to_user(
    box: BoundingBox, frame: _PageFrame, page_height: float
) -> tuple[float, float, float, float]:
    """A Docling box in the displayed frame -> user space ``(l, b, r, t)``.

    ``box`` may be TOPLEFT (grid cells) or BOTTOMLEFT over the displayed page
    height (table/picture prov); either way it is first made TOPLEFT, i.e. the
    ``(X, Y)`` of the forward mapping in the section comment above, and then
    that mapping is inverted:

        rotation   0:  x = X + x0    y = y1 - Y
        rotation  90:  x = Y + x0    y = X + y0
        rotation 180:  x = x1 - X    y = Y + y0
        rotation 270:  x = x1 - Y    y = y1 - X

    Both corners are mapped and re-sorted, since a rotation swaps which corner
    is which.
    """
    tl = (
        box
        if box.coord_origin == CoordOrigin.TOPLEFT
        else box.to_top_left_origin(page_height)
    )
    corners = [(tl.l, tl.t), (tl.r, tl.b)]
    if frame.rotation == 90:
        points = [(Y + frame.x0, X + frame.y0) for X, Y in corners]
    elif frame.rotation == 180:
        points = [(frame.x1 - X, Y + frame.y0) for X, Y in corners]
    elif frame.rotation == 270:
        points = [(frame.x1 - Y, frame.y1 - X) for X, Y in corners]
    else:
        points = [(X + frame.x0, frame.y1 - Y) for X, Y in corners]
    xs, ys = zip(*points, strict=True)
    return min(xs), min(ys), max(xs), max(ys)


def _prov_boxes(
    item: DocItem, doc: DoclingDocument, frames: dict[int, _PageFrame]
) -> list[PageBox]:
    """An item's boxes in user space, one per prov entry.

    Docling gives one ``prov`` per visual fragment of an item, each with its
    own page, bbox and ``charspan`` into the item's text, so a paragraph that
    wraps across a column or page break has several. Worked example from the
    ACN3-7-1962 test paper, ``#/texts/54`` (919 chars, page 3):

        prov 1  charspan (0, 97)    bbox l=66  t=102 r=294 b=81   BOTTOMLEFT
                "The results were analyzed using MatLab ... Regions of"
        prov 2  charspan (98, 919)  bbox l=311 t=711 r=539 b=535  BOTTOMLEFT
                "interests (cells) were masked ... Ca2-analysis)."

    becomes

        PageBox(page 3, x=66,  y=81,  w=228, h=21)   two-line tail, left column
        PageBox(page 3, x=311, y=535, w=228, h=176)  continuation, right column

    -- for text, Docling's own numbers (``x = l``, ``y = b``, ``h = t - b``),
    because text prov is already in user space. Drawn on the page, both sit
    exactly on the text and the sentence runs from one into the other. Table
    and picture prov is in the displayed frame instead and goes through
    ``_display_to_user`` (see the section comment). Items from DOCX/XLSX have no
    pages, so they get no boxes at all. Docling occasionally emits a zero-width
    or zero-height prov (7 of 14,640 anchors across the 94 prod papers); those
    cover nothing and are dropped.
    """
    boxes = []
    for prov in item.prov:
        page = doc.pages.get(prov.page_no)
        if page is None or page.size is None:  # DOCX and friends: no layout
            continue
        if isinstance(item, (TableItem, PictureItem)):
            # Layout-model output: displayed frame, needs the page's rotation.
            frame = _frame_for(frames, prov.page_no, page.size.width, page.size.height)
            l, b, r, t = _display_to_user(prov.bbox, frame, page.size.height)
        else:
            # Text-layer output: user space already. (TOPLEFT never occurs for
            # PDF text prov; the conversion is only there so the branch is total.)
            bl = (
                prov.bbox
                if prov.bbox.coord_origin == CoordOrigin.BOTTOMLEFT
                else prov.bbox.to_bottom_left_origin(page.size.height)
            )
            l, b, r, t = bl.l, bl.b, bl.r, bl.t
        if r <= l or t <= b:  # degenerate box: nothing to highlight
            continue
        boxes.append(PageBox(page_no=prov.page_no, x=l, y=b, width=r - l, height=t - b))
    return boxes


def _row_boxes(
    table: TableItem,
    doc: DoclingDocument,
    rendered_rows: int,
    frames: dict[int, _PageFrame],
) -> list[list[PageBox]]:
    """One box list per rendered data row, from the Docling cell grid, in user space.

    Rendered data row r is grid row r+1 (grid row 0 is the header). Only trusted
    when the counts agree; otherwise every row is empty and resolves to the
    table box. That is also the rule for a vision-rebuilt table: its rows come
    from the image, not the grid, but when it has exactly the grid's row count
    they are the same rows read top to bottom (decision 2026-09-30; before it
    every vision-corrected row was untrusted). Cells are TOPLEFT boxes in the
    displayed frame, like the table's own prov, so each row's union goes
    through ``_display_to_user``.
    """
    grid = table.data.grid
    if not table.prov or len(grid) != rendered_rows + 1:
        return [[] for _ in range(rendered_rows)]
    page_no = table.prov[0].page_no
    page = doc.pages.get(page_no)
    if page is None or page.size is None:
        return [[] for _ in range(rendered_rows)]
    frame = _frame_for(frames, page_no, page.size.width, page.size.height)

    rows: list[list[PageBox]] = []
    for grid_row in grid[1:]:
        cells = [c.bbox for c in grid_row if c.bbox is not None]
        if not cells:
            rows.append([])
            continue
        # Docling grid cells are TOPLEFT in practice; normalise defensively.
        tl = [
            b
            if b.coord_origin == CoordOrigin.TOPLEFT
            else b.to_top_left_origin(page.size.height)
            for b in cells
        ]
        # The row's rectangle is the union of its cells, still in the displayed
        # frame; converting the union is the same as converting each cell.
        union = BoundingBox(
            l=min(b.l for b in tl),
            t=min(b.t for b in tl),
            r=max(b.r for b in tl),
            b=max(b.b for b in tl),
            coord_origin=CoordOrigin.TOPLEFT,
        )
        l, b_, r, t = _display_to_user(union, frame, page.size.height)
        rows.append([PageBox(page_no=page_no, x=l, y=b_, width=r - l, height=t - b_)])
    return rows


def _with_anchor_column(markdown: str, table_id: str) -> tuple[list[str], int]:
    """Prepend an ``anchor`` column: header, separator, then table-N-row-R ids.

    Takes the '|' rows of the markdown (caption/notes around them are dropped).
    A line-level transform, so it works on Docling and vision tables alike.
    Returns the new lines and the number of data rows.

    Split on newlines only: Docling's export turns a cell's ``\\n`` into a
    space but leaves a bare ``\\r`` (16 prod tables have ``\\r\\n`` cells), and
    ``str.splitlines`` would cut the row there and lose the rest of it.
    """
    lines = [line.replace('\r', ' ').rstrip() for line in markdown.split('\n')]
    pipe_lines = [line for line in lines if _PIPE_LINE.match(line)]
    if not pipe_lines:
        return [], 0
    out = [f'| anchor {pipe_lines[0].lstrip()}']
    rest = pipe_lines[1:]
    if rest and _SEPARATOR_LINE.match(rest[0]):
        out.append(f'|---{rest[0].lstrip()}')
        rest = rest[1:]
    else:
        # A table with no separator is not GFM; give it one so it renders.
        columns = pipe_lines[0].count('|') - 1
        out.append('|---' * (columns + 1) + '|')
    for row_index, line in enumerate(rest):
        out.append(f'| {table_id}-row-{row_index} {line.lstrip()}')
    return out, len(rest)


def _table_text(
    table: TableItem,
    doc: DoclingDocument,
    serializer: MarkdownDocSerializer,
    frames: dict[int, _PageFrame],
    *,
    paper_id: int,
    supplement: bool,
) -> tuple[str, Anchor]:
    """One table -> its anchored text ('[table-N] caption' + tagged rows) and Anchor."""
    index = _docling_index(table)
    anchor_id = make_anchor_id(AnchorKind.TABLE, index, supplement)
    # Text: the vision rebuild if there is one, else Docling's own pipe table.
    vision_path = document_table_vision_markdown_path(paper_id, index, supplement)
    vision_corrected = vision_path.exists()
    source_md = (
        vision_path.read_text() if vision_corrected else table.export_to_markdown(doc)
    )
    pipe_lines, rendered_rows = _with_anchor_column(source_md, anchor_id)

    caption = serializer.serialize_captions(item=table).text.strip()
    lines = [f'[{anchor_id}] {caption}'.rstrip()]
    # The correction agent judged it corrupt and could not rebuild it: warn readers.
    if document_table_unrecovered_path(paper_id, index, supplement).exists():
        lines += ['', UNRECOVERED_TABLE_MARKER.format(table_id=index)]
    lines += ['', *pipe_lines]

    # Geometry: row rectangles when the rows shown line up with Docling's grid,
    # vision-rebuilt or not (_row_boxes checks the counts).
    anchor = Anchor(
        id=anchor_id,
        boxes=_prov_boxes(table, doc, frames),
        row_boxes=_row_boxes(table, doc, rendered_rows, frames),
    )
    return '\n'.join(lines), anchor


def _figure_text(
    picture: PictureItem,
    doc: DoclingDocument,
    serializer: MarkdownDocSerializer,
    frames: dict[int, _PageFrame],
    *,
    paper_id: int,
    supplement: bool,
) -> tuple[str, Anchor]:
    """One picture -> '[figure-N] ![caption](images/N.png)' and its Anchor."""
    index = _docling_index(picture)
    anchor_id = make_anchor_id(AnchorKind.FIGURE, index, supplement)
    caption = serializer.serialize_captions(item=picture).text.strip()
    image_path = document_image_path(paper_id, index, supplement)
    if image_path.exists():
        # Absolute path rooted at CAA_ROOT: the form the frontend rewrites to a URL.
        body = f'![{caption}]({image_path})'
    else:
        body = caption or '<!-- image -->'
    return f'[{anchor_id}] {body}', Anchor(
        id=anchor_id, boxes=_prov_boxes(picture, doc, frames)
    )


def _tagged(anchor_id: str, text: str) -> str:
    """'[id] text'; multi-line text (a fenced code block) gets the tag on its own line."""
    return f'[{anchor_id}]{chr(10) if chr(10) in text else " "}{text}'


def build_anchored(
    doc: DoclingDocument, *, paper_id: int, supplement: bool = False
) -> tuple[str, list[Anchor]]:
    """Render ``anchored.md`` and its ``anchors.json`` entries from a Docling document.

    Step by step:

    1. Build Docling's own markdown serializer, configured as ``raw.md`` is
       written today (no ``\\_`` escaping, raw HTML such as ``<sup>`` kept).
       We never ask it for the whole document, only for its *parts*.

    2. Walk ``serializer.get_parts()``: one block of output per body item, in
       reading order, each carrying ``spans`` -- the Docling items it was built
       from. Some items merge into one part, so a 159-item body gives ~117
       parts. The shapes seen, with real examples from the test paper:

           [SectionHeaderItem #/texts/1]                     '## Dominant mutations in ITPR3 ...'
           [TextItem #/texts/54]                             'Two missense variants ...'
           [TextItem #/texts/96 (caption), TableItem #/tables/0]     caption + pipe table
           [TextItem #/texts/70 (caption), PictureItem #/pictures/2] caption + '<!-- image -->'
           [PictureItem #/pictures/0]                        '<!-- image -->'  (uncaptioned logo)
           [ListItem #/texts/403, ListItem #/texts/404, ...] '1. Laura M...\\n2. Szigeti K...'

    3. Dispatch on the shape, first match wins:
         - has a TableItem     -> _table_text: '[table-N] caption', warning line
                                  if unrecovered, then the pipe table (vision
                                  rebuild if present) with the anchor column;
                                  one Anchor with table + row boxes
         - has a PictureItem   -> _figure_text: '[figure-N] ![caption](png)';
                                  one Anchor
         - all ListItems       -> one '[paragraph-N] 1. ...' line per item, each
                                  its own Anchor
         - heading/title       -> printed as '## ...', no id, no Anchor
         - any other TextItem  -> '[paragraph-N] text', one Anchor (two boxes
                                  if it wraps a column, see _prov_boxes)
         - anything else       -> its text, untagged (forms, key-value areas)
       A caption inside a table/figure part is consumed by that branch and
       gets no id of its own, which is why paragraph numbers have gaps:
       ``#/texts/96`` exists in Docling but is the caption of ``table-0``.

    4. Join the chunks with blank lines (one markdown block each) and return
       the anchors in the order their ids appear in the text.

    Deliberately not done here: headers get no id (never evidence, and the
    section classifier matches their text literally); nothing is searched for
    -- every id comes from ``self_ref``, so text and index cannot disagree.
    ``tables/N.vision.md``, ``N.unrecovered`` and ``images/N.png`` must already
    be in place under the document dir, since the text refers to them; that is
    why ``write_anchored_document`` calls this last.

    Coverage, from a census of every Docling item in the 94 dev-caa papers
    (+4 supplements) on 2026-09-29 -- what exists and where it goes:

        text 27135, caption 515, footnote 353, checkbox 23   -> [paragraph-N]
        list_item 4003 (in 283 list groups)                  -> [paragraph-N] each
        section_header 1967, title                           -> '## ...', untagged
        page_header 2044, page_footer 1429 (furniture layer) -> dropped by serializer
        table 214                                            -> [table-N] + rows
        picture 863                                          -> [figure-N]
        code 2 (both Wiley author lines misread as code)     -> [paragraph-N], fenced
        formula 5 (all empty text)                           -> never emitted
        inline groups 30 (several TextItems in one part)     -> one paragraph, all boxes
        key_value_area 164 / form_area 5 (58 multi-item parts, 397 items:
          'Received: ...' / 'Accepted: ...' blocks)          -> [paragraph-N] per child
        unspecified 252                                      -> children are parts of their own
        key_value_items 0, form_items 0                      -> would print untagged
        text inside pictures (263 in one paper)              -> excluded, cite figure-N
    """
    serializer = MarkdownDocSerializer(
        doc=doc, params=MarkdownParams(escape_html=False, escape_underscores=False)
    )
    # Each page's rotation and visible box, needed to bring table and picture
    # boxes into user space (see "Page geometry"). write_anchored_document copies
    # raw.pdf into the document dir before calling this, so it is there to read.
    frames = _page_frames(document_raw_path(paper_id, supplement))
    chunks: list[str] = []
    anchors: list[Anchor] = []

    for part in serializer.get_parts():
        # A part is one block of output; its spans are the items it was made from.
        items = [span.item for span in part.spans]
        table = next((i for i in items if isinstance(i, TableItem)), None)
        picture = next((i for i in items if isinstance(i, PictureItem)), None)

        if table is not None:
            # Captioned table: spans = [caption text, table]; one table anchor.
            text, anchor = _table_text(
                table, doc, serializer, frames, paper_id=paper_id, supplement=supplement
            )
            chunks.append(text)
            anchors.append(anchor)
        elif picture is not None:
            # Captioned picture: spans = [caption text, picture]; one figure anchor.
            text, anchor = _figure_text(
                picture,
                doc,
                serializer,
                frames,
                paper_id=paper_id,
                supplement=supplement,
            )
            chunks.append(text)
            anchors.append(anchor)
        elif items and all(isinstance(i, ListItem) for i in items):
            # A whole list is one part; tag each item as its own paragraph.
            lines = []
            for item in items:
                anchor_id = make_anchor_id(
                    AnchorKind.PARAGRAPH, _docling_index(item), supplement
                )
                lines.append(
                    f'[{anchor_id}] {serializer.serialize(item=item).text.strip()}'
                )
                anchors.append(
                    Anchor(id=anchor_id, boxes=_prov_boxes(item, doc, frames))
                )
            chunks.append('\n'.join(lines))
        elif items and isinstance(items[0], (SectionHeaderItem, TitleItem)):
            # Headings: printed as '## ...' with no id -- never evidence.
            chunks.append(part.text.strip())
        elif items and isinstance(items[0], TextItem) and part.text.strip():
            text_items = [i for i in items if isinstance(i, TextItem)]
            parent = items[0].parent.resolve(doc) if items[0].parent else None
            inline = isinstance(parent, GroupItem) and parent.label == GroupLabel.INLINE
            if len(text_items) > 1 and not inline:
                # A key-value or form area: the serializer folds its children into
                # one blank-line-separated part. Each child is its own paragraph.
                for item in text_items:
                    text = serializer.serialize(item=item).text.strip()
                    if not text:
                        continue
                    anchor_id = make_anchor_id(
                        AnchorKind.PARAGRAPH, _docling_index(item), supplement
                    )
                    chunks.append(_tagged(anchor_id, text))
                    anchors.append(
                        Anchor(id=anchor_id, boxes=_prov_boxes(item, doc, frames))
                    )
                continue
            # Ordinary paragraph (also an orphan caption whose table/figure was
            # dropped). An inline group merges several TextItems into one part:
            # the id is the first item's, the boxes are all of theirs.
            anchor_id = make_anchor_id(
                AnchorKind.PARAGRAPH, _docling_index(items[0]), supplement
            )
            chunks.append(_tagged(anchor_id, part.text.strip()))
            anchors.append(
                Anchor(
                    id=anchor_id,
                    boxes=[
                        box
                        for item in text_items
                        for box in _prov_boxes(item, doc, frames)
                    ],
                )
            )
        elif part.text.strip():
            # Anything else Docling can emit (forms, key-value areas): text, no id.
            chunks.append(part.text.strip())

    return '\n\n'.join(chunks) + '\n', anchors


# --- reading an anchored document back --------------------------------------

_TAG_LINE = re.compile(r'^\[([^\[\]\s]+)\](?:\s(.*))?$')
_ROW_LINE = re.compile(r'^\|\s*(\S+-row-\d+)\s*\|(.*)$')
_UNRECOVERED_PREFIX = '**[EXTRACTION WARNING'


def block_texts(markdown: str) -> dict[str, str]:
    """Map every id in an ``anchored.md`` to the text it tags.

    The reverse of ``build_anchored``: this is what ``verify_citations`` checks an
    agent's quotes against, and its keys are the set of ids that exist. A line
    state machine over the layout the builders produce (split on ``'\\n'`` only,
    as ``_with_anchor_column`` does, so a ``\\r`` inside a cell stays in the row):

    - ``[id] rest`` opens a block and closes the previous one (list items are
      consecutive tag lines with no blank between). A paragraph's text runs to
      the next blank line, continuing through an open ``\\`\\`\\``` fence; a
      figure's text is the alt text of ``![alt](path)``, or the bare caption.
    - Inside a table: the ``| anchor | ...`` header and each
      ``| table-N-row-R | c1 | c2 |`` row contribute ``| c1 | c2 |`` (anchor
      column removed, pipes kept, so a copied cell and a copied row both
      match); each row id also gets its own entry. The separator, blank lines
      and the unrecovered-table marker are skipped; any other line ends the
      table. The table's text is caption + header + rows joined by ``'\\n'``.
    - Headings, untagged text and fence markers belong to no id.
    """
    texts: dict[str, str] = {}
    current: str | None = None
    kind: AnchorKind | None = None
    lines: list[str] = []
    in_fence = False

    def close() -> None:
        if current is not None and current not in texts:
            texts[current] = '\n'.join(lines).strip()

    for line in markdown.split('\n'):
        tag = None if in_fence else _TAG_LINE.match(line)
        parsed = parse_anchor(tag.group(1)) if tag else None
        if tag and parsed is not None:
            close()
            current, kind, lines = tag.group(1), parsed.kind, []
            rest = (tag.group(2) or '').strip()
            if kind == AnchorKind.FIGURE:
                image = re.fullmatch(r'!\[(.*)\]\(.*\)', rest)
                rest = image.group(1) if image else rest
            if rest:
                lines.append(rest)
            continue
        if current is None:
            continue
        if kind == AnchorKind.TABLE:
            if not line.strip() or line.startswith(_UNRECOVERED_PREFIX):
                continue
            if _SEPARATOR_LINE.match(line):
                continue
            row = _ROW_LINE.match(line)
            if row:
                row_id, cells = row.group(1), '|' + row.group(2)
                lines.append(cells)
                texts.setdefault(row_id, cells.strip())
                continue
            if _PIPE_LINE.match(line):
                # The header: '| anchor | c1 | c2 |' -> '| c1 | c2 |'.
                lines.append('|' + line.split('|', 2)[2])
                continue
            close()
            current, kind, lines = None, None, []
            continue
        # Paragraph or figure caption: text to the next blank line, fences included.
        if line.strip().startswith('```'):
            in_fence = not in_fence
            lines.append(line)
            continue
        if not line.strip() and not in_fence:
            close()
            current, kind, lines = None, None, []
            continue
        lines.append(line)
    close()
    return texts


def paper_block_texts(paper_id: int) -> dict[str, str]:
    """Every id in a paper's anchored documents -> its text, main and supplement merged.

    The keys are exactly the ids that exist for the paper (``supp-`` ones
    included), which is what ``verify_citations`` checks an agent's output against.
    """
    texts = block_texts(document_anchored_md_path(paper_id).read_text())
    supplement = document_anchored_md_path(paper_id, supplement=True)
    if supplement.exists():
        texts.update(block_texts(supplement.read_text()))
    return texts


# --- building from plain markdown (XLSX supplements have no Docling document) --


def anchored_from_markdown(
    markdown: str, *, supplement: bool = True
) -> tuple[str, list[Anchor]]:
    """Tag a plain markdown document: paragraphs, pipe tables, images. No boxes."""
    chunks: list[str] = []
    anchors: list[Anchor] = []
    counters = dict.fromkeys(AnchorKind, 0)

    def next_id(kind: AnchorKind) -> str:
        """Sequential ids per kind -- there is no Docling index to borrow here."""
        anchor_id = make_anchor_id(kind, counters[kind], supplement)
        counters[kind] += 1
        return anchor_id

    # Blank-line-separated blocks, classified by shape: table, image, heading, else text.
    for block in re.split(r'\n\s*\n', markdown.strip()):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        if all(_PIPE_LINE.match(line) for line in lines):
            anchor_id = next_id(AnchorKind.TABLE)
            pipe_lines, rows = _with_anchor_column(block, anchor_id)
            chunks.append('\n'.join([f'[{anchor_id}]', '', *pipe_lines]))
            anchors.append(Anchor(id=anchor_id, row_boxes=[[] for _ in range(rows)]))
        elif len(lines) == 1 and _IMAGE_LINE.match(block):
            anchor_id = next_id(AnchorKind.FIGURE)
            chunks.append(f'[{anchor_id}] {block}')
            anchors.append(Anchor(id=anchor_id))
        elif _HEADING_LINE.match(block):
            chunks.append(block)
        else:
            anchor_id = next_id(AnchorKind.PARAGRAPH)
            chunks.append(f'[{anchor_id}] {block}')
            anchors.append(Anchor(id=anchor_id))

    return '\n\n'.join(chunks) + '\n', anchors
