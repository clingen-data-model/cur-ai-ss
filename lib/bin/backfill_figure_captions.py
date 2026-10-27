#!/usr/bin/env python3
"""Fill figure_descriptions.caption (and caption_source) for rows described
before the columns existed.

The Figure Description step stores the caption it read to the vision model
(migration b7e2f9c4d6a1); rows from before it carry none. This fills them
the way a re-run of the step would, without re-running it: from the figure
line's alt text in the anchored Markdown where it has one (DOCLING, or
ADJACENT when the parser adopted the block under the picture), else by
asking the vision model, shown the figure and the prose around it, which
block is its legend or what legend is printed in the image (``find_legend``;
``--no-model`` skips this). One small call per such row, each choice logged
so the run can be read before it is trusted. A figure with no answer is left
None, as a re-run would leave it. The anchored text on disk is not touched.

Fills only rows whose caption is None, so it is safe to re-run. A paper whose
files are missing is skipped and counted.

Usage:
    uv run python -m lib.bin.backfill_figure_captions [--no-model]
"""

import logging
import sys

from sqlalchemy.orm import Session

from lib.agents.figure_describer import find_legend
from lib.api.db import session_scope
from lib.core.logging import setup_logging
from lib.misc.images import image_to_data_url
from lib.misc.pdf.anchors import AnchorKind, make_anchor_id
from lib.misc.pdf.figure_text import figure_anchor
from lib.misc.pdf.paths import document_image_path
from lib.models.figure import FigureDescriptionDB
from lib.tasks.handlers import paper_figures

setup_logging()
logger = logging.getLogger(__name__)


def backfill_paper(session: Session, paper_id: int, ask_model: bool = True) -> int:
    """Fill the paper's caption-less rows from its anchored text, then, for
    those still without, from the model (``ask_model``); how many got one.
    Raises OSError when the paper's anchors file is missing."""
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
    # What the describer itself would be handed on a re-run.
    refs = {
        make_anchor_id(AnchorKind.FIGURE, f.image_id, f.is_supplement): f
        for f in paper_figures(paper_id)
    }
    filled = 0
    for row in rows:
        anchor = figure_anchor(row)
        ref = refs.get(anchor)
        if ref is None:
            continue  # no anchored text or image for it any more
        found = (
            (ref.caption, ref.caption_source)
            if ref.caption and ref.caption_source
            else None
        )
        if found is None and ask_model:
            legend = find_legend(
                image_to_data_url(
                    document_image_path(paper_id, row.image_id, row.is_supplement)
                ),
                ref.nearby,
                None,
            )
            found = (legend.text, legend.source) if legend else None
            logger.info(
                f'Paper {paper_id} {anchor}: model '
                + (f'{found[1]}: {found[0][:80]!r}' if found else 'found no legend')
            )
        if found is not None:
            row.caption, row.caption_source = found
            filled += 1
    return filled


def backfill(ask_model: bool = True) -> None:
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
                n = backfill_paper(session, paper_id, ask_model)
            logger.info(f'Paper {paper_id}: {n} captions filled')
            filled += n
        except OSError:
            logger.exception(f'Paper {paper_id}: files unreadable, skipped')
            skipped += 1

    logger.info(
        f'Done: {filled} captions filled across {len(paper_ids) - skipped} papers, '
        f'{skipped} papers skipped'
    )


if __name__ == '__main__':
    backfill(ask_model='--no-model' not in sys.argv[1:])
