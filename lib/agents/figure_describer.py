"""Describe every figure of a paper that extraction can read.

Not an agent. The step used to wrap the vision model in a text agent that
routed figures to a tool and stopped at the first pedigree; the agent never
saw an image, and copying the tool's answer into its output was a model step
that could drift. Now the handler shows every figure to the vision model
directly, twice at most:

1. ``classify_figure``: which of the readable kinds (``FigureKind``) the
   figure contains, from the image and its caption. A figure of no readable
   kind (a clinical photograph, a protein schematic, a frequency chart) is
   left undescribed.
2. ``describe_figure``: the description the downstream agents read. A
   pedigree gets ``PEDIGREE_VISION_PROMPT``; every other kind gets
   ``EVIDENCE_VISION_PROMPT``, which asks
   for what a curator would take from the figure: who was tested, for which
   variant, with what result and by what method. A figure of both sorts
   (a pedigree beside its Sanger traces) gets both, one after the other.

A figure the anchored document carries no caption for (Docling attached
none and the parser found no legend beside it, see the rule above
``_legend_item`` in lib/misc/pdf/anchors.py) gets a third question
first, ``find_legend``: shown the prose printed around it, which block is its
legend, or what legend is printed inside the image, or none. Only a readable
figure is asked, since only those get a row; the answer is the row's
``caption`` and the context for ``describe_figure``. The model sees what no
rule can: that five panels are redox titrations and belong to the "Figure 3"
legend two paragraphs down, or that the legend is drawn in the image.

A curator's notes (the paper-wide re-run context, or a re-run of this task
with context) go into every prompt, since the vision model is the only one
that can act on them.
"""

import logging
from dataclasses import dataclass
from typing import NamedTuple

from pydantic import BaseModel

from lib.agents.vision import vlm_describe
from lib.misc.images import image_to_data_url
from lib.misc.pdf.paths import document_image_path
from lib.models.figure import CaptionSource, FigureKind

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FigureRef:
    """A figure of the anchored document: the N of figure-N / supp-figure-N,
    which section it is in, and its caption as printed."""

    image_id: int
    is_supplement: bool
    caption: str | None = None
    # Where the caption came from (DOCLING or ADJACENT: the anchored text
    # carries it); None with the caption.
    caption_source: CaptionSource | None = None
    # The prose printed around the figure, (label, text) in reading order
    # (``figure_neighbourhoods``): what ``find_legend`` chooses from when the
    # caption is None.
    nearby: tuple[tuple[str, str], ...] = ()


class DescribedFigure(BaseModel):
    image_id: int
    is_supplement: bool
    kinds: list[FigureKind]
    # The caption the model was shown, and how it was arrived at, kept so the
    # row can be served with both.
    caption: str | None = None
    caption_source: CaptionSource | None = None
    description: str


class Legend(NamedTuple):
    """What ``find_legend`` found: the text and which way (a block the model
    chose, or its transcription of the image)."""

    text: str
    source: CaptionSource


# The vision model answers with exactly this when a figure is of no readable kind.
NO_READABLE_KIND = 'NONE'

_KIND_GUIDE = """- Pedigree: a family tree of squares and circles joined by lines of descent
- Chromatogram: Sanger sequencing traces (coloured peaks) showing a base change
- Gel: an electrophoresis gel, blot or restriction digest with lanes and bands
- Copy-number plot: MLPA, array or sequencing-depth ratios showing a deletion or duplication
- Read pileup: aligned sequencing reads in a genome browser view showing a variant
- Karyotype or FISH: a chromosome spread, an ideogram or fluorescent probe signals"""

CLASSIFY_PROMPT = f"""Which of these kinds of figure does this image contain? A figure may hold several panels of different kinds; name every kind that is present.

{_KIND_GUIDE}

Answer with the matching kind names exactly as written above, separated by semicolons, or exactly {NO_READABLE_KIND} if the image contains none of them (for example a clinical photograph, a protein or gene schematic, a chart of cohort frequencies, histology, a brain scan, a growth chart). Decide from the image itself; the caption is context, not the answer. Answer with the list only, nothing else."""

PEDIGREE_VISION_PROMPT = """First determine whether this image is a pedigree (family tree) diagram.
If it is NOT a pedigree diagram, respond with exactly NOT_A_PEDIGREE and nothing else.

Otherwise, extract detailed pedigree information from this diagram.

For the pedigree shown, enumerate ALL individuals visible, even if unclear or low resolution:
- Identifier (if present)
- Generation
- Left-to-right position
- Sex (if discernible, otherwise mark uncertain)
- Affected status (if discernible, otherwise mark uncertain)

Then describe:
- Parent-child relationships
- Sibling groups
- Affected individuals
- The proband if present
- Number of generations
- Any uncertainties due to image resolution or clarity

The caption printed below, when there is one, is the paper's legend for this figure. Read the meaning of marks from it -- an asterisk, a dot, a half-filled symbol, an arrow, a slash -- and say which individuals carry each mark and what the legend says it means. A mark the legend does not define is reported as undefined. The structure of the family comes from the image.

IMPORTANT: List every visible individual, even if some details are unclear. Do not infer missing details."""

# The pedigree prompt's own "not one after all" answer.
NOT_A_PEDIGREE = 'NOT_A_PEDIGREE'

EVIDENCE_VISION_PROMPT = """This figure shows genotyping or cytogenetic evidence ({kinds}). Describe what it establishes, so that a reader who cannot see the image can take from your description which individuals were tested, for which variant, and what each one's result was.

For every panel, lane or trace:
- The individual or sample it belongs to, as labelled (for example II-1, P3, "father", "control", "WT")
- The variant or region shown, as printed (c. or p. notation, gene, exon, probe, chromosome band)
- That individual's result: wild type, heterozygous, homozygous, hemizygous, deleted, duplicated, mosaic, present or absent, and what in the image shows it (a double peak, an extra band, a ratio)
- The method the panel evidences, if it can be told (Sanger sequencing, restriction digest, MLPA, array, read alignment, karyotype, FISH)

Keep it to what the image shows. Copy labels exactly as printed, do not infer sex or affected status, and say when a label or result cannot be read rather than guessing."""


# The model's answer when none of the blocks is the legend and none is drawn in the image.
NO_LEGEND = 'NONE'
# Prefix of an answer that transcribes a legend printed inside the image.
LEGEND_TEXT_PREFIX = 'TEXT:'

LEGEND_PROMPT = f"""The parsed text of this paper attaches no legend to this figure. Below are the blocks of text printed near it, in reading order, each with its id. Which block is this figure's legend: the text that names and explains this very figure, usually opening "Figure N." or "Fig. N"? Decide from the image: what it shows, its panel letters, any figure number drawn in it. A block that merely refers to the figure from the body text ("Figure 1 shows...") is not its legend, and a legend for a different figure is not either. A multi-panel figure may have been cut into one image per panel; the legend of the whole figure is then this panel's legend too.

Answer with exactly one line:
- the id of the legend block, or
- {LEGEND_TEXT_PREFIX} followed by the legend transcribed from the image, when the legend is printed inside the image itself and in none of the blocks, or
- {NO_LEGEND} when neither.

Blocks near the figure:
"""


def _nearby_section(nearby: tuple[tuple[str, str], ...]) -> str:
    return '\n'.join(f'[{label}] {text}' for label, text in nearby)


def parse_legend(
    answer: str | None, nearby: tuple[tuple[str, str], ...]
) -> Legend | None:
    """The legend a ``find_legend`` answer names: a nearby block's text when
    the answer is its label (brackets, quotes and a trailing period allowed;
    MODEL_CHOSEN), the transcription after ``TEXT:`` (MODEL_TRANSCRIBED),
    else None, so an answer that is not one of the three forms costs a
    missing caption, never a wrong one."""
    if answer is None:
        return None
    line = answer.strip().split('\n', 1)[0].strip()
    if line.upper().startswith(LEGEND_TEXT_PREFIX):
        text = line[len(LEGEND_TEXT_PREFIX) :].strip()
        return Legend(text, CaptionSource.MODEL_TRANSCRIBED) if text else None
    label = line.strip('[]`"\'. ')
    if label.upper() == NO_LEGEND:
        return None
    chosen = next((text for l, text in nearby if l == label), None)
    return Legend(chosen, CaptionSource.MODEL_CHOSEN) if chosen is not None else None


def find_legend(
    image_url: str, nearby: tuple[tuple[str, str], ...], notes: str | None
) -> Legend | None:
    """The legend of a figure the document attaches none to, as the vision
    model picks it from the prose around the figure or reads it off the
    image; None when it finds none or gives no usable answer."""
    if not nearby:
        return None
    answer = vlm_describe(
        image_url, LEGEND_PROMPT + _nearby_section(nearby) + _notes_section(notes)
    )
    legend = parse_legend(answer, nearby)
    if answer is not None and legend is None and answer.strip().upper() != NO_LEGEND:
        logger.warning(f'Legend answer named no block: {answer.strip()[:80]!r}')
    return legend


def _caption_section(caption: str | None) -> str:
    return f'\n\nCaption as printed in the paper:\n{caption}' if caption else ''


def _notes_section(notes: str | None) -> str:
    if not notes:
        return ''
    return (
        '\n\nA human curator has given instructions for this run; follow them '
        f'where they bear on this figure:\n{notes}'
    )


def parse_kinds(answer: str | None) -> list[FigureKind]:
    """The kinds named in a classification answer, in FigureKind order.

    None (a declined or truncated answer) and NONE both read as no kind; a
    token that is not a kind name is ignored, so a chatty answer costs at
    worst a missed kind, never a wrong one.
    """
    if answer is None:
        return []
    by_value = {kind.value.lower(): kind for kind in FigureKind}
    named = {
        by_value[token]
        for token in (
            part.strip().strip('-*.').strip().lower()
            for part in answer.replace('\n', ';').replace(',', ';').split(';')
        )
        if token in by_value
    }
    return [kind for kind in FigureKind if kind in named]


def classify_figure(
    image_url: str, caption: str | None, notes: str | None
) -> list[FigureKind]:
    """Which readable kinds the figure contains; [] when none or no answer."""
    answer = vlm_describe(
        image_url, CLASSIFY_PROMPT + _caption_section(caption) + _notes_section(notes)
    )
    kinds = parse_kinds(answer)
    if answer is None:
        logger.warning('Figure classification got no usable answer; skipping it')
    return kinds


def describe_figure(
    image_url: str, kinds: list[FigureKind], caption: str | None, notes: str | None
) -> str | None:
    """The description for a figure of these kinds, or None when the model
    gave no usable answer for any of them.

    Both prompts are shown the caption. For a pedigree it is the legend
    that defines the marks (the pedigree prompt used to go without it, and a
    model reading an asterisk the legend defined reported it as undefined);
    for the other kinds its panel labels are often the only link from a trace
    to a person. A figure of both sorts gets both texts, the pedigree first.
    """
    parts: list[str] = []
    if FigureKind.PEDIGREE in kinds:
        pedigree = vlm_describe(
            image_url,
            PEDIGREE_VISION_PROMPT + _caption_section(caption) + _notes_section(notes),
        )
        # A half-described pedigree stored as authoritative is worse than none,
        # so None stays None; NOT_A_PEDIGREE is the model changing its mind.
        if pedigree is not None and pedigree.strip() != NOT_A_PEDIGREE:
            parts.append(pedigree)
    evidence_kinds = [kind for kind in kinds if kind != FigureKind.PEDIGREE]
    if evidence_kinds:
        evidence = vlm_describe(
            image_url,
            EVIDENCE_VISION_PROMPT.format(
                kinds=', '.join(kind.value for kind in evidence_kinds)
            )
            + _caption_section(caption)
            + _notes_section(notes),
        )
        if evidence is not None:
            parts.append(f'## Genotyping evidence\n\n{evidence}' if parts else evidence)
    return '\n\n'.join(parts) if parts else None


def describe_figures(
    paper_id: int, figures: list[FigureRef], notes: str | None = None
) -> list[DescribedFigure]:
    """Classify every figure and describe the readable ones, in the order given.

    A readable figure with no caption is asked its legend first
    (``find_legend``), so the description is written with it and the row
    stores it. A figure of no readable kind, or one the model would not
    describe, is left out. A provider or network error propagates: not reaching the model
    is a task failure, not a finding about the paper.
    """
    described: list[DescribedFigure] = []
    for figure in figures:
        label = f'{"supp-" if figure.is_supplement else ""}figure-{figure.image_id}'
        image_url = image_to_data_url(
            document_image_path(paper_id, figure.image_id, figure.is_supplement)
        )
        kinds = classify_figure(image_url, figure.caption, notes)
        if not kinds:
            logger.info(f'Paper {paper_id} {label}: no readable kind')
            continue
        logger.info(f'Paper {paper_id} {label}: {", ".join(k.value for k in kinds)}')
        caption, source = figure.caption, figure.caption_source
        if caption is None:
            legend = find_legend(image_url, figure.nearby, notes)
            if legend is not None:
                caption, source = legend
            logger.info(
                f'Paper {paper_id} {label}: legend '
                + (f'{source}: {caption[:60]!r}' if caption else 'not found')
            )
        description = describe_figure(image_url, kinds, caption, notes)
        if description is None:
            logger.warning(f'Paper {paper_id} {label}: no usable description')
            continue
        described.append(
            DescribedFigure(
                image_id=figure.image_id,
                is_supplement=figure.is_supplement,
                kinds=kinds,
                caption=caption,
                caption_source=source,
                description=description,
            )
        )
    return described
