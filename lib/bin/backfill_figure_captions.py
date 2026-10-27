#!/usr/bin/env python3
"""Fill figure_descriptions.caption for rows described before the column existed.

The Figure Description step stores the caption it read to the vision model
(migration b7e2f9c4d6a1); rows from before it carry none. The caption is the
alt text of the figure's line in the anchored Markdown on disk, or, when
Docling attached none, the orphan legend printed right beside the figure
(``figure_captions`` in lib/misc/pdf/anchors.py, the same rule the parser now
applies when it builds the document). That is exactly what a re-run of the
step would read, so this copies it instead of re-running (no model call). A
figure with neither is asked of the vision model the way the step now asks
(``find_legend``: shown the figure and the prose around it, which block is
its legend, or what legend is printed in the image), unless ``--no-model``;
one small call per such row, each choice logged so the run can be read
before it is trusted. A figure with no answer is left None, as a re-run
would leave it. The anchored text itself is not rewritten: consuming an
orphan paragraph into its figure would retire an id that stored citations
may point at.

Fills only rows whose caption is None, so it is safe to re-run. A paper whose
anchored text is missing is skipped and counted.

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
from lib.misc.pdf.anchors import (
    adjacent_legends,
    attached_captions,
    document_anchored_md_path,
    figure_neighbourhoods,
    load_anchors,
)
from lib.misc.pdf.figure_text import figure_anchor
from lib.misc.pdf.paths import document_image_path
from lib.models.figure import CaptionSource, FigureDescriptionDB

setup_logging()
logger = logging.getLogger(__name__)


class _Document:
    """What the paper's anchored text says about its figures, main and
    supplement merged: each figure's caption with its source where the text
    gives one, and the prose around every figure for the model."""

    def __init__(self, paper_id: int) -> None:
        self.captions: dict[str, tuple[str, CaptionSource]] = {}
        self.nearby: dict[str, list[tuple[str, str]]] = {}
        for supplement in (False, True):
            path = document_anchored_md_path(paper_id, supplement=supplement)
            if supplement and not path.exists():
                continue
            markdown = path.read_text()
            adopted = {
                a.id
                for a in load_anchors(paper_id, supplement=supplement)
                if a.caption_adopted
            }
            for figure_id, text in adjacent_legends(markdown).items():
                self.captions[figure_id] = (text, CaptionSource.ADJACENT)
            for figure_id, text in attached_captions(markdown).items():
                source = (
                    CaptionSource.ADJACENT
                    if figure_id in adopted
                    else CaptionSource.DOCLING
                )
                self.captions[figure_id] = (text, source)
            self.nearby.update(figure_neighbourhoods(markdown))


def backfill_paper(session: Session, paper_id: int, ask_model: bool = True) -> int:
    """Fill the paper's caption-less rows from its anchored text, then, for
    those still without, from the model (``ask_model``); how many got one.
    Raises OSError when the paper has no anchored text."""
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
    document = _Document(paper_id)
    filled = 0
    for row in rows:
        anchor = figure_anchor(row)
        found = document.captions.get(anchor)
        if found is None and ask_model:
            image = document_image_path(paper_id, row.image_id, row.is_supplement)
            if image.exists():
                legend = find_legend(
                    image_to_data_url(image),
                    tuple(document.nearby.get(anchor, [])),
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
            logger.exception(f'Paper {paper_id}: anchored text unreadable, skipped')
            skipped += 1

    logger.info(
        f'Done: {filled} captions filled across {len(paper_ids) - skipped} papers, '
        f'{skipped} papers skipped'
    )


if __name__ == '__main__':
    backfill(ask_model='--no-model' not in sys.argv[1:])
