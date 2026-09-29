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
is the existence of ``tables/N.vision.md``, and its one geometric consequence
(no trustworthy row rectangles) shows up as empty ``row_boxes`` entries.
"""

import json
import re
from enum import StrEnum
from pathlib import Path

from docling_core.transforms.serializer.markdown import (
    MarkdownDocSerializer,
    MarkdownParams,
)
from docling_core.types.doc import (
    DocItem,
    DoclingDocument,
    ListItem,
    PictureItem,
    SectionHeaderItem,
    TableItem,
    TextItem,
    TitleItem,
)
from docling_core.types.doc.base import BoundingBox, CoordOrigin
from pydantic import BaseModel

from lib.misc.pdf.paths import (
    UNRECOVERED_TABLE_MARKER,
    document_anchored_md_path,
    document_anchors_path,
    document_image_path,
    document_table_unrecovered_path,
    document_table_vision_markdown_path,
)


class AnchorKind(StrEnum):
    """What an id points at; also the word the id starts with."""

    PARAGRAPH = 'paragraph'  # #/texts/N: paragraph, list item, caption
    TABLE = 'table'  # #/tables/N; may carry a -row-R suffix
    FIGURE = 'figure'  # #/pictures/N


SUPPLEMENT_PREFIX = 'supp-'

# Self-describing, hyphen-only ids: paragraph-54, table-1, table-1-row-7,
# figure-2, supp-table-1-row-7. A couple of tokens more per block than
# p54/t1.r7, and far harder for an agent to mangle or a human to misread.
ANCHOR_RE = re.compile(
    rf'^({SUPPLEMENT_PREFIX})?({"|".join(AnchorKind)})-(\d+)(?:-row-(\d+))?$'
)

_PIPE_LINE = re.compile(r'^\s*\|')
_SEPARATOR_LINE = re.compile(r'^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$')
_IMAGE_LINE = re.compile(r'^!\[.*\]\(.*\)\s*$')
_HEADING_LINE = re.compile(r'^#{1,6}\s')


class PageBox(BaseModel):
    """A rectangle on a PDF page, in points, TOP-LEFT origin (what the viewer draws)."""

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
    # trusted (vision-corrected table, or the Docling grid does not line up
    # with the rendered rows); resolve it to the table's own boxes instead.
    row_boxes: list[list[PageBox]] = []


class ParsedAnchor(BaseModel):
    """The pieces of an id: 'supp-table-1-row-7' -> (True, 'table', 1, 7)."""

    supplement: bool
    kind: AnchorKind
    index: int
    row: int | None = None


def parse_anchor(anchor_id: str) -> ParsedAnchor | None:
    """Validate an id against the grammar and split it; None if malformed."""
    match = ANCHOR_RE.match(anchor_id)
    if not match:
        return None
    prefix, kind, index, row = match.groups()
    if row is not None and kind != AnchorKind.TABLE:
        return None
    return ParsedAnchor(
        supplement=prefix is not None,
        kind=AnchorKind(kind),
        index=int(index),
        row=int(row) if row is not None else None,
    )


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


def _anchor_id(kind: AnchorKind, index: int, supplement: bool) -> str:
    """Format an id: (TABLE, 3, True) -> 'supp-table-3'."""
    prefix = SUPPLEMENT_PREFIX if supplement else ''
    return f'{prefix}{kind}-{index}'


def _page_box(page_no: int, bbox: BoundingBox, page_height: float) -> PageBox:
    """Convert a Docling bbox (either origin) to the viewer's top-left x/y/w/h."""
    top_left = bbox.to_top_left_origin(page_height)
    return PageBox(
        page_no=page_no,
        x=top_left.l,
        y=top_left.t,
        width=top_left.r - top_left.l,
        height=top_left.b - top_left.t,
    )


def _prov_boxes(item: DocItem, doc: DoclingDocument) -> list[PageBox]:
    """An item's page boxes, one per prov entry.

    Docling gives one ``prov`` per visual fragment of an item, each with its
    own page, bbox and ``charspan`` into the item's text, so a paragraph that
    wraps across a column or page break has several. Worked example from the
    ACN3-7-1962 test paper, ``#/texts/54`` (919 chars, page 3, height 782.36):

        prov 1  charspan (0, 97)    bbox l=66  t=102 r=294 b=81   BOTTOMLEFT
                "The results were analyzed using MatLab ... Regions of"
        prov 2  charspan (98, 919)  bbox l=311 t=711 r=539 b=535  BOTTOMLEFT
                "interests (cells) were masked ... Ca2-analysis)."

    becomes

        PageBox(page 3, x=66,  y=680.6, w=228, h=21)   two-line tail, left column
        PageBox(page 3, x=311, y=70.9,  w=228, h=176)  continuation, right column

    (``y = 782.36 - t``; ``h = t - b``). Drawn on the page, both sit exactly on
    the text and the sentence runs from one into the other. Items from DOCX/
    XLSX have no pages, so they get no boxes at all.
    """
    boxes = []
    for prov in item.prov:
        page = doc.pages.get(prov.page_no)
        if page is None or page.size is None:  # DOCX and friends: no layout
            continue
        boxes.append(_page_box(prov.page_no, prov.bbox, page.size.height))
    return boxes


def _row_boxes(
    table: TableItem, doc: DoclingDocument, rendered_rows: int
) -> list[list[PageBox]]:
    """One box list per rendered data row, from the Docling cell grid.

    Rendered data row r is grid row r+1 (grid row 0 is the header). Only trusted
    when the counts agree; otherwise every row is empty and resolves to the
    table box. Cell boxes are already TOP-LEFT, unlike ``prov``.
    """
    grid = table.data.grid
    if not table.prov or len(grid) != rendered_rows + 1:
        return [[] for _ in range(rendered_rows)]
    page_no = table.prov[0].page_no
    page = doc.pages.get(page_no)
    if page is None or page.size is None:
        return [[] for _ in range(rendered_rows)]

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
        l, t = min(b.l for b in tl), min(b.t for b in tl)
        r, b_ = max(b.r for b in tl), max(b.b for b in tl)
        rows.append([PageBox(page_no=page_no, x=l, y=t, width=r - l, height=b_ - t)])
    return rows


def _pipe_lines(markdown: str) -> list[str]:
    """Just the '|' rows of a markdown table, dropping caption/notes around it."""
    return [line for line in markdown.splitlines() if _PIPE_LINE.match(line)]


def _with_anchor_column(pipe_lines: list[str], table_id: str) -> tuple[list[str], int]:
    """Prepend an ``anchor`` column: header, separator, then table-N-row-R ids.

    A line-level transform, so it works on Docling and vision tables alike.
    Returns the new lines and the number of data rows.
    """
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


def _table_is_unrecovered(paper_id: int, index: int, supplement: bool) -> bool:
    """The correction agent judged the table corrupt and could not rebuild it."""
    return document_table_unrecovered_path(paper_id, index, supplement).exists()


def _table_text(
    table: TableItem,
    doc: DoclingDocument,
    serializer: MarkdownDocSerializer,
    *,
    paper_id: int,
    supplement: bool,
) -> tuple[str, Anchor]:
    """One table -> its anchored text ('[table-N] caption' + tagged rows) and Anchor."""
    index = _docling_index(table)
    anchor_id = _anchor_id(AnchorKind.TABLE, index, supplement)
    # Text: the vision rebuild if there is one, else Docling's own pipe table.
    vision_path = document_table_vision_markdown_path(paper_id, index, supplement)
    vision_corrected = vision_path.exists()
    source_md = (
        vision_path.read_text() if vision_corrected else table.export_to_markdown(doc)
    )
    pipe_lines, rendered_rows = _with_anchor_column(_pipe_lines(source_md), anchor_id)

    caption = serializer.serialize_captions(item=table).text.strip()
    lines = [f'[{anchor_id}] {caption}'.rstrip()]
    if _table_is_unrecovered(paper_id, index, supplement):
        lines += ['', UNRECOVERED_TABLE_MARKER.format(table_id=index)]
    lines += ['', *pipe_lines]

    # Geometry: row rectangles only when the rows shown are Docling's own rows.
    row_boxes = (
        [[] for _ in range(rendered_rows)]
        if vision_corrected
        else _row_boxes(table, doc, rendered_rows)
    )
    anchor = Anchor(id=anchor_id, boxes=_prov_boxes(table, doc), row_boxes=row_boxes)
    return '\n'.join(lines), anchor


def _figure_text(
    picture: PictureItem,
    doc: DoclingDocument,
    serializer: MarkdownDocSerializer,
    *,
    paper_id: int,
    supplement: bool,
) -> tuple[str, Anchor]:
    """One picture -> '[figure-N] ![caption](images/N.png)' and its Anchor."""
    index = _docling_index(picture)
    anchor_id = _anchor_id(AnchorKind.FIGURE, index, supplement)
    caption = serializer.serialize_captions(item=picture).text.strip()
    image_path = document_image_path(paper_id, index, supplement)
    if image_path.exists():
        # Absolute path rooted at CAA_ROOT: the form the frontend rewrites to a URL.
        body = f'![{caption}]({image_path})'
    else:
        body = caption or '<!-- image -->'
    return f'[{anchor_id}] {body}', Anchor(
        id=anchor_id, boxes=_prov_boxes(picture, doc)
    )


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
    """
    serializer = MarkdownDocSerializer(
        doc=doc, params=MarkdownParams(escape_html=False, escape_underscores=False)
    )
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
                table, doc, serializer, paper_id=paper_id, supplement=supplement
            )
            chunks.append(text)
            anchors.append(anchor)
        elif picture is not None:
            # Captioned picture: spans = [caption text, picture]; one figure anchor.
            text, anchor = _figure_text(
                picture, doc, serializer, paper_id=paper_id, supplement=supplement
            )
            chunks.append(text)
            anchors.append(anchor)
        elif items and all(isinstance(i, ListItem) for i in items):
            # A whole list is one part; tag each item as its own paragraph.
            lines = []
            for item in items:
                anchor_id = _anchor_id(
                    AnchorKind.PARAGRAPH, _docling_index(item), supplement
                )
                lines.append(
                    f'[{anchor_id}] {serializer.serialize(item=item).text.strip()}'
                )
                anchors.append(Anchor(id=anchor_id, boxes=_prov_boxes(item, doc)))
            chunks.append('\n'.join(lines))
        elif items and isinstance(items[0], (SectionHeaderItem, TitleItem)):
            # Headings: printed as '## ...' with no id -- never evidence.
            chunks.append(part.text.strip())
        elif items and isinstance(items[0], TextItem) and part.text.strip():
            # Ordinary paragraph (also an orphan caption whose table/figure was
            # dropped). An inline group merges several TextItems into one part:
            # the id is the first item's, the boxes are all of theirs.
            anchor_id = _anchor_id(
                AnchorKind.PARAGRAPH, _docling_index(items[0]), supplement
            )
            text = part.text.strip()
            # Multi-line text (a fenced code block) needs the tag on its own line.
            chunks.append(f'[{anchor_id}]{chr(10) if chr(10) in text else " "}{text}')
            anchors.append(
                Anchor(
                    id=anchor_id,
                    boxes=[
                        box
                        for item in items
                        if isinstance(item, TextItem)
                        for box in _prov_boxes(item, doc)
                    ],
                )
            )
        elif part.text.strip():
            # Anything else Docling can emit (forms, key-value areas): text, no id.
            chunks.append(part.text.strip())

    return '\n\n'.join(chunks) + '\n', anchors


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
        anchor_id = _anchor_id(kind, counters[kind], supplement)
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
            pipe_lines, rows = _with_anchor_column(lines, anchor_id)
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
