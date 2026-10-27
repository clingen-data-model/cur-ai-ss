"""Figure descriptions spliced into the anchored text, where the figure is.

The agents read a figure's description in place: a quoted block right under
its ``[figure-N]`` line, headed by the kinds the figure shows, so the result
of a Sanger trace sits next to the sentence that cites it and a pedigree next
to its legend. ``anchored.md`` on disk is never changed; the splice happens
at read time (``paper_text`` in lib/tasks/handlers.py, the ``/document``
endpoint), so a Figure Description re-run changes what is read next without
touching the parse.

A quote copied from a description cites the figure's anchor. The citation
check accepts it (``figure_texts``), the PDF view highlights the picture
(the quote is not in the legend, so the figure's own boxes stay), and the
Markdown view highlights the figure and the quoted span.
"""

import re

from lib.misc.pdf.anchors import AnchorKind, make_anchor_id
from lib.models.figure import FigureDescriptionDB

FIGURE_DESCRIPTION_HEAD = 'Figure description'

# A figure's tag line: `[figure-N] ![alt](path)` or `[supp-figure-N]` alone.
_FIGURE_LINE = re.compile(r'^\[((?:supp-)?figure-\d+)\](?:\s|$)')
# A figure line that carries a legend: alt text, or bare text with no image.
_FIGURE_LINE_WITH_LEGEND = re.compile(
    r'^\[(?:supp-)?figure-\d+\]\s+(?:!\[.+?\]\(|[^!])'
)
FIGURE_LEGEND_HEAD = 'Figure legend'


def figure_anchor(figure: FigureDescriptionDB) -> str:
    return make_anchor_id(AnchorKind.FIGURE, figure.image_id, figure.is_supplement)


def figure_description_block(
    figure: FigureDescriptionDB, *, with_legend: bool = False
) -> str:
    """The description as a markdown blockquote, headed by what the figure
    shows and by whose words these are. Every line is quoted, blank ones
    included, so the block holds together as one quote under the figure.

    ``with_legend`` puts the stored caption first, as the paper's words: for
    a figure whose line in the text carries none, so the legend the
    describer found for it (``find_legend``) reaches the agents under the
    figure it belongs to rather than only as a paragraph somewhere near it.
    """
    kinds = ', '.join(figure.kinds)
    head = (
        f'**{FIGURE_DESCRIPTION_HEAD}** ({kinds}): a reading of this figure '
        "written by a vision model, not the paper's own words."
    )
    lines = [head, '', *figure.description.strip().split('\n')]
    if with_legend and figure.caption:
        lines = [f'**{FIGURE_LEGEND_HEAD}**: {figure.caption}', '', *lines]
    return '\n'.join(f'> {line}' if line.strip() else '>' for line in lines)


def splice_figure_descriptions(
    markdown: str, figures: list[FigureDescriptionDB]
) -> str:
    """The anchored markdown with each described figure's block right under
    its ``[figure-N]`` line. Figures with no description are left as they are;
    descriptions whose figure is not in the text are dropped."""
    by_anchor = {figure_anchor(f): f for f in figures}
    if not by_anchor:
        return markdown
    out: list[str] = []
    for line in markdown.split('\n'):
        out.append(line)
        tag = _FIGURE_LINE.match(line)
        if tag and tag.group(1) in by_anchor:
            out.append(
                figure_description_block(
                    by_anchor[tag.group(1)],
                    with_legend=not _FIGURE_LINE_WITH_LEGEND.match(line),
                )
            )
    return '\n'.join(out)


def figure_texts(
    texts: dict[str, str], figures: list[FigureDescriptionDB]
) -> dict[str, str]:
    """``texts`` (anchor id -> block text, as ``paper_block_texts`` builds it)
    with each described figure's text extended by its description, and by
    its stored caption when the text carries none, so a quote copied from
    either checks out against its figure."""
    out = dict(texts)
    for figure in figures:
        anchor = figure_anchor(figure)
        if anchor not in out:
            continue
        legend = figure.caption if not out[anchor] else None
        out[anchor] = '\n'.join(
            part for part in (out[anchor], legend, figure.description) if part
        )
    return out
