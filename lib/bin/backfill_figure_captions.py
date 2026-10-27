#!/usr/bin/env python3
"""Fill figure_descriptions.caption for rows described before the column existed.

The Figure Description step stores the caption it read to the vision model
(migration b7e2f9c4d6a1); rows from before it carry none. The caption is the
alt text of the figure's line in the anchored Markdown on disk, or, when
Docling attached none, the orphan legend printed right beside the figure
(``figure_captions`` in lib/misc/pdf/anchors.py, the same rule the parser now
applies when it builds the document). That is exactly what a re-run of the
step would read, so this copies it instead of re-running (no model call). A
figure with neither is left None, as a re-run would leave it. The anchored
text itself is not rewritten: consuming an orphan paragraph into its figure
would retire an id that stored citations may point at.

Fills only rows whose caption is None, so it is safe to re-run. A paper whose
anchored text is missing is skipped and counted.

Usage:
    uv run python -m lib.bin.backfill_figure_captions
"""

import logging

from sqlalchemy.orm import Session

from lib.api.db import session_scope
from lib.core.logging import setup_logging
from lib.misc.pdf.anchors import paper_figure_captions
from lib.misc.pdf.figure_text import figure_anchor
from lib.models.figure import FigureDescriptionDB

setup_logging()
logger = logging.getLogger(__name__)


def backfill_paper(session: Session, paper_id: int) -> int:
    """Fill the paper's caption-less rows from its anchored text; how many
    got one. Raises OSError when the paper has no anchored text."""
    rows = (
        session.query(FigureDescriptionDB)
        .filter(
            FigureDescriptionDB.paper_id == paper_id,
            FigureDescriptionDB.caption.is_(None),
        )
        .all()
    )
    if not rows:
        return 0
    captions = paper_figure_captions(paper_id)
    filled = 0
    for row in rows:
        caption = captions.get(figure_anchor(row))
        if caption is not None:
            row.caption = caption
            filled += 1
    return filled


def backfill() -> None:
    with session_scope() as session:
        paper_ids = [
            i
            for (i,) in session.query(FigureDescriptionDB.paper_id)
            .filter(FigureDescriptionDB.caption.is_(None))
            .distinct()
            .order_by(FigureDescriptionDB.paper_id)
        ]

    filled = 0
    skipped = 0
    for paper_id in paper_ids:
        # One session per paper so one paper's missing files roll back nothing else.
        try:
            with session_scope() as session:
                n = backfill_paper(session, paper_id)
            logger.info(f'Paper {paper_id}: {n} captions filled')
            filled += n
        except OSError:
            logger.exception(f'Paper {paper_id}: anchored text unreadable, skipped')
            skipped += 1

    logger.info(
        f'Done: {filled} captions filled across {len(paper_ids) - skipped} papers, '
        f'{skipped} papers skipped'
    )


if __name__ == '__main__':
    backfill()
