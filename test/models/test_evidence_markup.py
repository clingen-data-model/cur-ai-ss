"""Tidying evidence quotes for display.

A quote is stored verbatim so it can be matched back to the page. When a table
has been rebuilt from its image, that verbatim text is rich markdown -- footnote
markers as <sup>, in-cell line breaks as <br> -- and Streamlit escapes tags, so
a curator reads them literally. These are real quotes from paper 96.
"""

from lib.models.evidence_block import EvidenceBlock
from lib.models.evidence_block import strip_markup as clean_quote


def test_footnote_markers_are_dropped():
    quote = '| *FH Dallas-1 | 1 | Fs 3<sup>g</sup> | ΔC | 1 | American |'
    assert clean_quote(quote) == '| *FH Dallas-1 | 1 | Fs 3 | ΔC | 1 | American |'


def test_a_line_break_inside_a_cell_becomes_a_space():
    """<br> splits a word in two; dropping it outright would join them."""
    assert clean_quote('| *FH San<br>Francisco | 2 | C6W<sup>i</sup> |').startswith(
        '| *FH San Francisco | 2 | C6W |'
    )


def test_a_superscript_that_is_data_is_kept():
    """Only one- and two-letter superscripts read as footnote markers."""
    assert clean_quote('activity was 10<sup>6</sup> units') == 'activity was 10^6 units'
    assert clean_quote('H<sub>2</sub>O') == 'H_2O'


def test_the_value_itself_survives():
    for quote, expected in (
        ('Stop 4<sup>h</sup> | TGG→TAG', 'Stop 4 | TGG→TAG'),
        (
            '**A. Signal Sequence (exon 1)**<br>*FH Dallas-1',
            '**A. Signal Sequence (exon 1)** *FH Dallas-1',
        ),
    ):
        assert clean_quote(quote) == expected


def test_a_quote_with_no_markup_is_untouched():
    quote = 'The proband was diagnosed at 9 years of age.'
    assert clean_quote(quote) == quote


def test_a_less_than_sign_that_is_not_a_tag_is_kept():
    """LDL receptor activity is reported as "<2"; that is data, not markup."""
    assert (
        clean_quote('| LDL receptor activity | <2 |')
        == '| LDL receptor activity | <2 |'
    )


def test_a_block_is_cleaned_as_it_is_built():
    """Every write path goes through the model, so none has to remember."""
    block = EvidenceBlock[str](
        value='Fs 3',
        reasoning='Taken from <b>Table 2</b>',
        quote='| *FH San<br>Francisco | Fs 3<sup>g</sup> | <2 |',
    )
    assert block.quote == '| *FH San Francisco | Fs 3 | <2 |'
    assert block.reasoning == 'Taken from Table 2'


def test_cleaning_a_block_twice_changes_nothing():
    """The backfill and the validator both run over stored rows."""
    once = EvidenceBlock[str](value='Fs 3', reasoning='r', quote='Fs 3<sup>g</sup>')
    twice = EvidenceBlock[str](
        value=once.value, reasoning=once.reasoning, quote=once.quote
    )
    assert twice.quote == once.quote == 'Fs 3'


def test_a_block_with_no_quote_is_left_alone():
    block = EvidenceBlock[None](value=None, reasoning='Not reported in the paper.')
    assert block.quote is None


def test_the_cleanup_script_only_touches_text_a_curator_reads():
    """Structural fields are left alone; a rewrite that reordered or retyped
    them would be a silent change to data nothing asked to clean."""
    from lib.bin.strip_evidence_markup import _clean

    block = {
        'value': 'Fs 3',
        'reasoning': 'From <b>Table 2</b>',
        'quote': 'Fs 3<sup>g</sup>',
        'table_id': None,
        'image_id': 3,
        'is_supplement': False,
    }
    assert _clean(block) == 2
    assert block == {
        'value': 'Fs 3',
        'reasoning': 'From Table 2',
        'quote': 'Fs 3',
        'table_id': None,
        'image_id': 3,
        'is_supplement': False,
    }


def test_the_cleanup_script_reports_nothing_to_do_on_clean_text():
    from lib.bin.strip_evidence_markup import _clean

    assert (
        _clean({'quote': 'activity was <2% of normal', 'reasoning': 'onset <1 year'})
        == 0
    )


def test_the_scripts_copy_of_the_rules_matches_the_models():
    """The script carries its own copy so it can run on a deployment that
    predates the model change. They must not drift."""
    from lib.bin.strip_evidence_markup import strip_markup as script_version

    for sample in (
        '| *FH San<br>Francisco | Fs 3<sup>g</sup> | <2 |',
        'activity was 10<sup>6</sup> units',
        'H<sub>2</sub>O',
        'From <b>Table 2</b>',
        'age at onset <1 year',
        'plain text with no markup at all',
    ):
        assert script_version(sample) == clean_quote(sample)


def test_hgvs_operators_are_not_mistaken_for_a_tag():
    """These papers use "<" as data ("<2" of normal activity) and ">" as data
    (c.361G>C). A catch-all <[^>]+> matches from one to the other and eats what
    lies between: "LDL activity <2 and c.361G>C" came out as "LDL activity C".
    Both strings below are real evidence from the corpus.
    """
    for text in (
        'LDL activity <2 and c.361G>C',
        'onset <1 year, variant c.98T>G',
        '| A3174-21 | M | Arabic | c.361G>C | p.Glu121Gln |',
    ):
        assert clean_quote(text) == text


def test_a_line_break_between_two_hgvs_values_still_goes():
    quote = '| A3174-21 | <2 | c.361G>C<br>c.1745C>A |'
    assert clean_quote(quote) == '| A3174-21 | <2 | c.361G>C c.1745C>A |'


def test_text_with_no_markup_is_returned_untouched():
    """Not merely unchanged in meaning -- byte-identical. A quote is verbatim so
    it can be matched back against words extracted from the page, and reflowing
    its whitespace on the way past would be a modification nobody asked for.
    """
    spaced = 'Homozygote patient    |           |          |'
    assert clean_quote(spaced) == spaced


def test_a_malformed_tag_does_not_raise():
    """Evidence is model-written text; it will eventually contain something odd."""
    for text in ('unclosed <sup>g', 'stray </sup> close', 'a < b > c', '<<>>', ''):
        clean_quote(text)


def test_clinical_less_than_phrasing_survives():
    """ "<third percentile" and "<5th centile" are ordinary phrasing in these
    papers, and the "<" is followed by a letter, so anything that follows the
    HTML spec treats it as opening a tag.

    This is why the rules here are a pattern over known tag names and not
    html.parser. The parser is correct by construction about "<2", but a 3.12
    patch release hardened it to discard incomplete markup at end of input, so
    it silently drops everything after an unclosed "<letter". Measured on the
    same string with the same code: Python 3.12.0 returned it whole, 3.12.3
    returned "52 cm (". Losing clinical text on some deployments and not others
    is worse than leaving an unrecognised tag on screen, which is at least
    visible and recoverable.
    """
    for text in (
        'Her occipitofrontal circumference was 52 cm (<third percentile).',
        'growth was <5th centile for age',
        'below <lower limit of normal',
    ):
        assert clean_quote(text) == text
