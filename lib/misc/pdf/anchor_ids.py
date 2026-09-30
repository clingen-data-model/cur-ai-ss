"""The anchor id grammar, on its own so ``lib.models`` can import it.

``lib.misc.pdf.anchors`` builds the anchored documents and imports ``fitz`` and
``docling_core`` to do so; the evidence models only need to recognise an id
(``Citation.anchor``) and must not drag those into every model import. This
module is stdlib only. ``anchors.py`` re-exports everything here.
"""

import re
from enum import StrEnum

from pydantic import BaseModel


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


class ParsedAnchor(BaseModel):
    """The pieces of an id: 'supp-table-1-row-7' -> (True, 'table', 1, 7)."""

    supplement: bool
    kind: AnchorKind
    index: int
    row: int | None = None


def parse_anchor(anchor_id: str) -> ParsedAnchor | None:
    """Validate an id against the grammar and split it; None if malformed.

    Stricter than ``ANCHOR_RE`` alone: a ``-row-`` suffix is only valid on a table.
    """
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
