"""Figure descriptions spliced into the anchored text at their figure."""

from lib.misc.pdf.figure_text import (
    figure_description_block,
    figure_texts,
    splice_figure_descriptions,
)
from lib.models.figure import FigureDescriptionDB

PAPER = (
    '## Results\n\n'
    '[paragraph-1] Sanger sequencing confirmed the variant (Figure 2).\n\n'
    '[figure-0] ![Figure 1. Photographs](x/0.png)\n\n'
    '[figure-2] ![](x/2.png)\n\n'
    '[paragraph-3] More text.\n'
)


def _figure(
    image_id: int, kinds: list[str], description: str, supplement=False, caption=None
):
    return FigureDescriptionDB(
        image_id=image_id,
        is_supplement=supplement,
        kinds=kinds,
        caption=caption,
        description=description,
    )


def test_block_is_a_headed_blockquote_with_every_line_quoted():
    figure = _figure(2, ['Pedigree', 'Gel'], 'II-1: affected\n\nLane 2: digested')

    assert figure_description_block(figure) == (
        '> **Figure description** (Pedigree, Gel): a reading of this figure '
        "written by a vision model, not the paper's own words.\n"
        '>\n'
        '> II-1: affected\n'
        '>\n'
        '> Lane 2: digested'
    )


def test_splice_puts_each_block_right_under_its_figure_line():
    figure = _figure(2, ['Chromatogram'], 'Subject 1: single T peak')

    spliced = splice_figure_descriptions(PAPER, [figure])

    assert spliced == (
        '## Results\n\n'
        '[paragraph-1] Sanger sequencing confirmed the variant (Figure 2).\n\n'
        '[figure-0] ![Figure 1. Photographs](x/0.png)\n\n'
        '[figure-2] ![](x/2.png)\n'
        + figure_description_block(figure)
        + '\n\n[paragraph-3] More text.\n'
    )


def test_splice_leaves_the_text_alone_without_descriptions():
    assert splice_figure_descriptions(PAPER, []) == PAPER
    # A description whose figure is not in this text (the supplement's, say).
    assert splice_figure_descriptions(PAPER, [_figure(2, ['Gel'], 'd', True)]) == PAPER


def test_splice_matches_supplement_ids_only_in_the_supplement():
    supplement = '[supp-figure-0] ![Fig S1](x/0.png)\n'
    main_figure = _figure(0, ['Gel'], 'main')
    supp_figure = _figure(0, ['Pedigree'], 'supp', True)

    assert splice_figure_descriptions(supplement, [main_figure, supp_figure]) == (
        supplement.rstrip('\n') + '\n' + figure_description_block(supp_figure) + '\n'
    )


def test_figure_texts_extend_the_legend_with_the_description():
    texts = {
        'paragraph-1': 'Sanger ...',
        'figure-0': 'Figure 1. Photographs',
        'figure-2': '',
    }
    figures = [
        _figure(2, ['Chromatogram'], 'Subject 1: single T peak'),
        _figure(0, ['Gel'], 'never described but listed'),
        _figure(7, ['Gel'], 'no such figure'),
    ]

    extended = figure_texts(texts, figures)

    assert extended == {
        'paragraph-1': 'Sanger ...',
        'figure-0': 'Figure 1. Photographs\nnever described but listed',
        'figure-2': 'Subject 1: single T peak',
    }
    assert texts['figure-2'] == ''  # the input is not changed


def test_splice_puts_a_stored_legend_under_a_figure_line_that_has_none():
    """figure-2's line carries no alt text, so the legend the describer found
    for it leads the block, as the paper's words; figure-0's line already
    carries its legend, so its block does not repeat it."""
    figures = [
        _figure(0, ['Pedigree'], 'the family', caption='Figure 1. Photographs'),
        _figure(2, ['Gel'], 'lane 2 digested', caption='Figure 2. Restriction digest'),
    ]

    spliced = splice_figure_descriptions(PAPER, figures)

    assert (
        '[figure-2] ![](x/2.png)\n'
        '> **Figure legend**: Figure 2. Restriction digest\n'
        '>\n'
        '> **Figure description** (Gel)'
    ) in spliced
    assert (
        '[figure-0] ![Figure 1. Photographs](x/0.png)\n'
        '> **Figure description** (Pedigree)'
    ) in spliced
    assert spliced.count('Figure 1. Photographs') == 1


def test_figure_texts_add_a_stored_legend_only_where_the_text_has_none():
    """A quote from a legend the describer found checks out against its
    figure; a figure whose text already carries its legend gets the
    description alone, so the legend is not doubled."""
    texts = {'figure-0': 'Figure 1. Photographs', 'figure-2': ''}
    figures = [
        _figure(0, ['Pedigree'], 'the family', caption='Figure 1. Photographs'),
        _figure(2, ['Gel'], 'lane 2 digested', caption='Figure 2. Restriction digest'),
    ]

    assert figure_texts(texts, figures) == {
        'figure-0': 'Figure 1. Photographs\nthe family',
        'figure-2': 'Figure 2. Restriction digest\nlane 2 digested',
    }
