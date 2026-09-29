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

# Self-describing, hyphen-only ids: paragraph-54, table-1, table-1-row-7,
# figure-2, supp-table-1-row-7. A couple of tokens more per block than
# p54/t1.r7, and far harder for an agent to mangle or a human to misread.
ANCHOR_RE = re.compile(r'^(supp-)?(paragraph|table|figure)-(\d+)(?:-row-(\d+))?$')

SUPPLEMENT_PREFIX = 'supp-'

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
    id: str
    boxes: list[PageBox] = []
    # Tables only: one entry per rendered data row, so the row ids are known
    # from this file alone. A row's list is empty when its rectangle cannot be
    # trusted (vision-corrected table, or the Docling grid does not line up
    # with the rendered rows); resolve it to the table's own boxes instead.
    row_boxes: list[list[PageBox]] = []


class ParsedAnchor(BaseModel):
    supplement: bool
    kind: str  # 'paragraph' | 'table' | 'figure'
    index: int
    row: int | None = None


def parse_anchor(anchor_id: str) -> ParsedAnchor | None:
    match = ANCHOR_RE.match(anchor_id)
    if not match:
        return None
    prefix, kind, index, row = match.groups()
    if row is not None and kind != 'table':
        return None
    return ParsedAnchor(
        supplement=prefix is not None,
        kind=kind,
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
    md_path = document_anchored_md_path(paper_id, supplement)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md)
    document_anchors_path(paper_id, supplement).write_text(
        json.dumps([a.model_dump() for a in anchors], indent=1)
    )


def load_anchors(paper_id: int, supplement: bool = False) -> list[Anchor]:
    path = document_anchors_path(paper_id, supplement)
    return [Anchor.model_validate(a) for a in json.loads(path.read_text())]


# --- building from a DoclingDocument ------------------------------------------


def _docling_index(item: DocItem) -> int:
    return int(item.self_ref.rsplit('/', 1)[1])


def _anchor_id(kind: str, index: int, supplement: bool) -> str:
    prefix = SUPPLEMENT_PREFIX if supplement else ''
    return f'{prefix}{kind}-{index}'


def _page_box(page_no: int, bbox: BoundingBox, page_height: float) -> PageBox:
    top_left = bbox.to_top_left_origin(page_height)
    return PageBox(
        page_no=page_no,
        x=top_left.l,
        y=top_left.t,
        width=top_left.r - top_left.l,
        height=top_left.b - top_left.t,
    )


def _prov_boxes(item: DocItem, doc: DoclingDocument) -> list[PageBox]:
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
    return document_table_unrecovered_path(paper_id, index, supplement).exists()


def _table_text(
    table: TableItem,
    doc: DoclingDocument,
    serializer: MarkdownDocSerializer,
    *,
    paper_id: int,
    supplement: bool,
) -> tuple[str, Anchor]:
    index = _docling_index(table)
    anchor_id = _anchor_id('table', index, supplement)
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
    index = _docling_index(picture)
    anchor_id = _anchor_id('figure', index, supplement)
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

    Walks the markdown serializer's parts (one per body item, in reading order;
    a captioned table/figure part spans its caption too, a list part spans its
    items) so the text is exactly what Docling would print, plus the ids.
    Headers are printed untagged: they are never evidence, and the section
    classifier matches them literally. Table files (``tables/N.vision.md``,
    ``N.unrecovered``) and ``images/N.png`` must already be in place under
    the document dir, since the text refers to them.
    """
    serializer = MarkdownDocSerializer(
        doc=doc, params=MarkdownParams(escape_html=False, escape_underscores=False)
    )
    chunks: list[str] = []
    anchors: list[Anchor] = []

    for part in serializer.get_parts():
        items = [span.item for span in part.spans]
        table = next((i for i in items if isinstance(i, TableItem)), None)
        picture = next((i for i in items if isinstance(i, PictureItem)), None)

        if table is not None:
            text, anchor = _table_text(
                table, doc, serializer, paper_id=paper_id, supplement=supplement
            )
            chunks.append(text)
            anchors.append(anchor)
        elif picture is not None:
            text, anchor = _figure_text(
                picture, doc, serializer, paper_id=paper_id, supplement=supplement
            )
            chunks.append(text)
            anchors.append(anchor)
        elif items and all(isinstance(i, ListItem) for i in items):
            lines = []
            for item in items:
                anchor_id = _anchor_id('paragraph', _docling_index(item), supplement)
                lines.append(
                    f'[{anchor_id}] {serializer.serialize(item=item).text.strip()}'
                )
                anchors.append(Anchor(id=anchor_id, boxes=_prov_boxes(item, doc)))
            chunks.append('\n'.join(lines))
        elif items and isinstance(items[0], (SectionHeaderItem, TitleItem)):
            chunks.append(part.text.strip())
        elif items and isinstance(items[0], TextItem):
            # Includes an orphan caption whose table/figure was not emitted.
            first = items[0]
            anchor_id = _anchor_id('paragraph', _docling_index(first), supplement)
            chunks.append(f'[{anchor_id}] {part.text.strip()}')
            anchors.append(Anchor(id=anchor_id, boxes=_prov_boxes(first, doc)))
        elif part.text.strip():
            chunks.append(part.text.strip())

    return '\n\n'.join(chunks) + '\n', anchors


# --- building from plain markdown (XLSX supplements have no Docling document) --


def anchored_from_markdown(
    markdown: str, *, supplement: bool = True
) -> tuple[str, list[Anchor]]:
    """Tag a plain markdown document: paragraphs, pipe tables, images. No boxes."""
    chunks: list[str] = []
    anchors: list[Anchor] = []
    counters = {'paragraph': 0, 'table': 0, 'figure': 0}

    def next_id(kind: str) -> str:
        anchor_id = _anchor_id(kind, counters[kind], supplement)
        counters[kind] += 1
        return anchor_id

    for block in re.split(r'\n\s*\n', markdown.strip()):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        if all(_PIPE_LINE.match(line) for line in lines):
            anchor_id = next_id('table')
            pipe_lines, rows = _with_anchor_column(lines, anchor_id)
            chunks.append('\n'.join([f'[{anchor_id}]', '', *pipe_lines]))
            anchors.append(Anchor(id=anchor_id, row_boxes=[[] for _ in range(rows)]))
        elif len(lines) == 1 and _IMAGE_LINE.match(block):
            anchor_id = next_id('figure')
            chunks.append(f'[{anchor_id}] {block}')
            anchors.append(Anchor(id=anchor_id))
        elif _HEADING_LINE.match(block):
            chunks.append(block)
        else:
            anchor_id = next_id('paragraph')
            chunks.append(f'[{anchor_id}] {block}')
            anchors.append(Anchor(id=anchor_id))

    return '\n\n'.join(chunks) + '\n', anchors
