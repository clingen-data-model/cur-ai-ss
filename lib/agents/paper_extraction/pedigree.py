"""Pass 0: which figure is the pedigree, and what it shows.

Asked about the figures alone, the model read paper 89's three pedigrees
correctly -- including an individual the single-pass run had marked affected
where the figure shows an open symbol.

It picks an image_id from the list it is shown, so a wrong answer is out of
range and catchable, rather than a plausible number pointing at another figure.
"""

import logging
from typing import Any

from lib.agents.paper_extraction._shared import _run
from lib.misc.gcs import image_to_data_url
from lib.misc.pdf.paths import pdf_image_path
from lib.models.paper import PedigreeExtractionOutput

logger = logging.getLogger(__name__)

PEDIGREE_INSTRUCTIONS = """You are shown every figure extracted from one research paper,
each labelled with its image_id. Identify which single figure contains a pedigree diagram.

Return that figure's image_id, chosen from the labels you were given. Never invent one.
If no figure contains a pedigree, set found=false and leave image_id null.

Describe the pedigree individual by individual, so a curator can check it: for each person,
their generation and position (I-1, II-3), sex, affected status, and relationship to the
others. Read the symbols rather than the caption -- a filled symbol is affected, an open
one unaffected, a diagonal slash means deceased, a square is male and a circle female.
Where a paper shows several families in one figure, describe each separately."""


def _identify_pedigree_sync(
    paper_id: int, figures: list[dict]
) -> PedigreeExtractionOutput | None:
    content: list[dict[str, Any]] = [
        {'type': 'text', 'text': 'Figures from this paper:'}
    ]
    for fig in figures:
        path = pdf_image_path(paper_id, fig['image_id'])
        if not path.exists():
            continue
        content.append({'type': 'text', 'text': f'image_id: {fig["image_id"]}'})
        content.append(
            {
                'type': 'image_url',
                'image_url': {'url': image_to_data_url(path), 'detail': 'high'},
            }
        )

    if len(content) == 1:
        return PedigreeExtractionOutput(found=False)

    result = _run(
        'pedigree', paper_id, PedigreeExtractionOutput, PEDIGREE_INSTRUCTIONS, content
    )

    # The model chose from a list we supplied, so an out-of-range answer is a
    # bug we can see rather than a wrong figure shown to a curator.
    if result and result.found and result.image_id is not None:
        known = {f['image_id'] for f in figures}
        if result.image_id not in known:
            logger.warning(
                f'Paper {paper_id}: pedigree pass returned image_id '
                f'{result.image_id}, which is not among {sorted(known)}; discarding'
            )
            return PedigreeExtractionOutput(found=False)
    return result
