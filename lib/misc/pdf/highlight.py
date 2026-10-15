import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, cast

import fitz
from Bio.Align import PairwiseAligner
from pydantic import BaseModel

from lib.misc.pdf.anchor_ids import AnchorKind, parse_anchor
from lib.misc.pdf.anchors import (
    PageBox,
    _PageFrame,
    boxes_for_anchor,
    caption_boxes_for_anchor,
    load_anchors,
    on_page,
    page_frames,
    user_to_display,
)
from lib.misc.pdf.parse import Polygon, WordLoc
from lib.misc.pdf.paths import document_raw_path, document_words_json_path
from lib.models.evidence_block import Citation


class GrobidAnnotation(BaseModel):
    """GROBID-style coordinate with top-left origin (y increases downward)."""

    page: int
    x: float
    y: float
    width: float
    height: float
    color: str
    border: str = 'solid'


def parse_hex_color(color_str: str) -> tuple[float, float, float]:
    if color_str.startswith('#'):
        hex_str = color_str.lstrip('#')
        if len(hex_str) == 6:
            try:
                r = int(hex_str[0:2], 16) / 255.0
                g = int(hex_str[2:4], 16) / 255.0
                b = int(hex_str[4:6], 16) / 255.0
                return (r, g, b)
            except ValueError:
                pass

    raise ValueError(f'Invalid color: "{color_str}". Use a hex code (e.g., "#FF0000")')


def merge_adjacent_polygons(
    words: list[WordLoc],
) -> list[Polygon]:
    """
    Merge adjacent polygons if they are aligned and close together.

    Args:
        words: List of WordLoc objects (each with 4 corner coordinates)

    Returns:
        List of merged Polygon objects
    """
    if not words:
        return []

    y_tol, x_tol = 2, 15
    merged: list[Polygon] = [words[0].to_polygon()]

    for word in words[1:]:
        prev = merged[-1]
        same_top = abs(prev.y0 - word.y0) < y_tol
        same_bottom = abs(prev.y3 - word.y3) < y_tol
        small_gap = (word.x0 - prev.x1) < x_tol

        if same_top and same_bottom and small_gap:
            # Merge: extend previous polygon's right edge to current word's right edge
            merged[-1] = Polygon(
                x0=prev.x0,
                y0=prev.y0,
                x1=word.x1,
                y1=word.y1,
                x2=word.x2,
                y2=word.y2,
                x3=prev.x3,
                y3=prev.y3,
            )
        else:
            # Add as separate polygon
            merged.append(word.to_polygon())

    return merged


def find_best_match(query: str, words: list[WordLoc]) -> list[WordLoc] | None:
    def get_aligner() -> PairwiseAligner:
        aligner = PairwiseAligner()
        aligner.mode = 'local'  # Smith-Waterman local alignment
        aligner.match_score = 1.0  # Match/mismatch scoring
        aligner.mismatch_score = -0.5  # Affine Gap penalties
        aligner.open_gap_score = -2
        aligner.extend_gap_score = -0.001
        return aligner

    def normalize(token: str) -> str:
        """Normalize tokens to improve fuzzy matching."""
        token = token.lower()
        token = token.replace('\u00ad', '')  # soft hyphen
        token = token.replace('\u2010', '-')  # hyphen
        token = token.replace('\u2011', '-')  # non-breaking hyphen
        token = token.replace('\u2012', '-')  # figure dash
        token = token.replace('\u2013', '-')  # en dash
        token = token.replace('\u2014', '-')  # em dash
        token = token.replace('\u2015', '-')  # horizontal bar
        token = token.replace('|', '')  # markdown table delimiters
        token = re.sub(r'\s+', ' ', token)
        return token

    def get_word_to_offset(normalized_words: list[str]) -> list[tuple[int, int]]:
        offsets = []
        start = 0
        for normalized_word in normalized_words:
            end = start + len(normalized_word)
            offsets.append((start, end))
            start = end + 1
        return offsets

    def get_words_from_alignment(
        aligned_blocks: list[tuple[int, int]],
        word_to_offset: list[tuple[int, int]],
        words: list[WordLoc],
    ) -> list[WordLoc]:
        matched_words = []
        for pdf_start, pdf_end in aligned_blocks:
            for i, (start, end) in enumerate(word_to_offset):
                if end > pdf_start and start < pdf_end:
                    matched_words.append(words[i])
        return matched_words

    n_words, n_query = len(words), len(query.split())
    if n_words == 0 or n_query == 0:
        return None

    normalized_query = normalize(query)
    normalized_words = [normalize(w.word) for w in words]
    word_to_offset = get_word_to_offset(normalized_words)
    aligner = get_aligner()
    alignments = aligner.align(normalized_query, ' '.join(normalized_words))
    if not alignments:
        return None
    return get_words_from_alignment(alignments[0].aligned[1], word_to_offset, words)


# --- highlighting by citation ---------------------------------------------------
#
# Evidence cites anchors (lib/misc/pdf/anchors.py); a highlight is the anchor's
# precomputed boxes, never a re-found quote. The only matching left is *narrowing*:
# a paragraph or table-row citation with a quote highlights the quote's words
# instead of the whole block, and the search is confined to the words inside
# that block's own boxes, so a miss can widen a highlight but never misplace it.
#
# Anchor boxes are in PDF user space; words.json is not, on a rotated page (see
# ``word_frame_to_user``). The block's boxes are brought into the words' frame
# for the search, the quote is matched and merged there, where a line of text
# runs along x, and the result goes back to user space for the viewer.


def _displayed_height(frame: _PageFrame) -> float:
    return frame.x1 - frame.x0 if frame.rotation in (90, 270) else frame.y1 - frame.y0


def word_frame_to_user(x: float, y: float, frame: _PageFrame) -> tuple[float, float]:
    """A point in docling-parse's word frame -> PDF user space.

    docling-parse writes words.json in the *displayed* orientation -- the page
    as a viewer shows it, ``/Rotate`` applied -- with a bottom-left origin and
    y up, not in user space as the rest of the page geometry is. Measured, not
    assumed: on every one of the 19 rotated pages in prod (2026-10-15, ten at
    90 and nine at 270) the words fit only the rotated page size, and on paper
    87 page 4 (603 x 783, /Rotate 90) PyMuPDF puts "62" at user x 229..236,
    y 286..294 where words.json has x 286..294, y 367..374: (y, 603 - x).

    So a word point is first the displayed top-left ``(X, Y)`` of the mapping
    in anchors.py's "Page geometry" notes, with the y flip against the
    displayed height, and then that mapping's inverse. An unrotated page is a
    passthrough: there the two frames coincide, and every unrotated paper has
    been highlighted on that basis.
    """
    if frame.rotation == 0:
        return x, y
    X, Y = x, _displayed_height(frame) - y
    if frame.rotation == 90:
        return Y + frame.x0, X + frame.y0
    if frame.rotation == 180:
        return frame.x1 - X, Y + frame.y0
    return frame.x1 - Y, frame.y1 - X


def _user_box_to_word_frame(
    box: PageBox, frames: dict[int, _PageFrame]
) -> PageBox | None:
    """The inverse of ``word_frame_to_user`` for a box; None for a page not in the PDF."""
    frame = frames.get(box.page_no)
    if frame is None:
        return None
    if frame.rotation == 0:
        return box
    placed = user_to_display(box, frames)
    if placed is None:
        return None
    X, Y, width, height = placed
    return PageBox(
        page_no=box.page_no,
        x=X,
        y=_displayed_height(frame) - Y - height,
        width=width,
        height=height,
    )


def words_within(
    boxes: list[PageBox], words: list[WordLoc], tol: float = 2.0
) -> list[WordLoc]:
    """The words whose centre lies inside any of the boxes, in their input order.

    Both are in the words' own frame (``word_frame_to_user``) with 1-based page
    numbers. ``tol`` grows each box by a couple of points so a word sitting
    exactly on a box edge still counts.
    """
    by_page: defaultdict[int, list[PageBox]] = defaultdict(list)
    for box in boxes:
        by_page[box.page_no].append(box)
    inside = []
    for word in words:
        cx = (word.x0 + word.x1 + word.x2 + word.x3) / 4
        cy = (word.y0 + word.y1 + word.y2 + word.y3) / 4
        for box in by_page.get(int(word.page_idx), ()):
            if (
                box.x - tol <= cx <= box.x + box.width + tol
                and box.y - tol <= cy <= box.y + box.height + tol
            ):
                inside.append(word)
                break
    return inside


def _polygon_boxes(
    page_no: int, polygons: list[Polygon], frame: _PageFrame
) -> list[PageBox]:
    """Merged word polygons -> user-space boxes (corner order does not matter)."""
    boxes = []
    for p in polygons:
        corners = [
            word_frame_to_user(x, y, frame)
            for x, y in ((p.x0, p.y0), (p.x1, p.y1), (p.x2, p.y2), (p.x3, p.y3))
        ]
        xs, ys = zip(*corners, strict=True)
        boxes.append(
            PageBox(
                page_no=page_no,
                x=min(xs),
                y=min(ys),
                width=max(xs) - min(xs),
                height=max(ys) - min(ys),
            )
        )
    return boxes


def boxes_to_grobid_annotations(
    boxes: list[PageBox],
    frames: dict[int, _PageFrame],
    color: tuple[float, float, float],
) -> list[GrobidAnnotation]:
    """User-space boxes -> annotations on the displayed page (``user_to_display``)."""
    css = f'rgb({color[0] * 255.0},{color[1] * 255.0},{color[2] * 255.0})'
    annotations = []
    for box in boxes:
        placed = user_to_display(box, frames)
        if placed is None:
            continue
        x, y, width, height = placed
        annotations.append(
            GrobidAnnotation(
                page=box.page_no, x=x, y=y, width=width, height=height, color=css
            )
        )
    return annotations


def citations_to_grobid_annotations(
    paper_id: int,
    citations: list[Citation],
    color: tuple[float, float, float],
) -> list[GrobidAnnotation]:
    """Every citation's boxes on the main PDF, in citation order.

    Per citation: a supplement, unknown or malformed anchor contributes nothing
    (the supplement has no PDF view; nothing here raises). A paragraph or a
    table row with a quote is narrowed to the quote's words when they align
    inside the block's boxes, else it is the whole block: for a row that is
    its own rectangle, or the table's when the row's is not trusted, and a
    Docling grid row can span most of a page (a transposed table read as a
    few tall rows), so the cell is what the quote points at. A table cited
    whole, and a figure with no quote, are their boxes as stored; a figure with
    a quote narrows to it inside its legend, else stays the picture.
    """
    anchors = load_anchors(paper_id)
    frames = page_frames(document_raw_path(paper_id))
    words: list[WordLoc] | None = None  # read once, only if a quote needs it

    annotations: list[GrobidAnnotation] = []
    for citation in citations:
        parsed = parse_anchor(citation.anchor)
        if parsed is None or parsed.supplement:
            continue
        # A stale anchors.json (parsed before clipped text was left out) can
        # still hold a box off its page; it covers nothing a reader can see.
        boxes = [
            b
            for b in boxes_for_anchor(citation.anchor, anchors)
            if b.page_no in frames and on_page(b, frames[b.page_no])
        ]
        if not boxes:
            continue
        # A figure narrows only inside its legend: the picture holds no words
        # of the paper, and a quote on a figure can only come from the legend.
        # A table cited whole never narrows.
        search_boxes = boxes
        if parsed.kind == AnchorKind.FIGURE:
            search_boxes = caption_boxes_for_anchor(citation.anchor, anchors)
        narrowable = (
            parsed.kind == AnchorKind.PARAGRAPH
            or parsed.row is not None
            or (parsed.kind == AnchorKind.FIGURE and bool(search_boxes))
        )
        if narrowable and citation.quote.strip():
            if words is None:
                words = _load_words(paper_id)
            word_boxes = [
                b
                for b in (_user_box_to_word_frame(b, frames) for b in search_boxes)
                if b is not None
            ]
            matched = find_best_match(citation.quote, words_within(word_boxes, words))
            if matched:
                by_page: defaultdict[int, list[WordLoc]] = defaultdict(list)
                for word in matched:
                    by_page[int(word.page_idx)].append(word)
                boxes = [
                    box
                    for page_no, page_words in by_page.items()
                    if page_no in frames
                    for box in _polygon_boxes(
                        page_no, merge_adjacent_polygons(page_words), frames[page_no]
                    )
                ]
        annotations.extend(boxes_to_grobid_annotations(boxes, frames, color))
    return annotations


def _load_words(paper_id: int) -> list[WordLoc]:
    path = document_words_json_path(paper_id)
    if not path.exists():
        return []
    return [WordLoc.model_validate(w) for w in json.loads(path.read_text())]
