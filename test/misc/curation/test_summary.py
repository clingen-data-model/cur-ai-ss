import pytest

from lib.misc.curation.summary import format_af, variant_heading
from lib.models.variant import HarmonizedVariantDB, VariantDB


@pytest.mark.parametrize(
    ('af', 'expected'),
    [
        # Below 5e-6, where five fixed decimals printed 0.00000.
        (0.0000018588304982037502, '0.00000186'),
        # One allele in gnomAD's 1.6 million: the rarest it reports.
        (6.237292e-7, '0.00000062'),
        (0.00001785969, '0.00001786'),
        (0.000254237288, '0.00025424'),
        (0.0123456789, '0.01234568'),
        (0.5, '0.50000000'),
        (1.0, '1.00000000'),
        (0.0, '0'),
    ],
)
def test_format_af_keeps_eight_decimal_places(af: float, expected: str) -> None:
    assert format_af(af) == expected


def test_format_af_never_uses_scientific_notation() -> None:
    assert 'e' not in format_af(1e-12)


def _variant(
    hgvs_c: str | None,
    hgvs_p: str | None,
    harmonized_c: str | None = None,
    harmonized_p: str | None = None,
    harmonized: bool = True,
) -> VariantDB:
    variant = VariantDB(id=7, hgvs_c=hgvs_c, hgvs_p=hgvs_p, variant_evidence={})
    if harmonized:
        variant.harmonized_variant = HarmonizedVariantDB(
            hgvs_c=harmonized_c, hgvs_p=harmonized_p
        )
    return variant


def test_variant_named_once_when_the_paper_agrees() -> None:
    # The deck printed the harmonized c. as the title and the paper's c. and
    # p. again in the body.
    title, reported = variant_heading(
        _variant(
            'c.98T>G', 'p.Leu33Arg', 'NM_004341.5:c.98T>G', 'NP_004332.2:p.(Leu33Arg)'
        )
    )
    assert title == 'NM_004341.5:c.98T>G (p.(Leu33Arg))'
    assert reported is None


def test_one_letter_protein_is_the_same_change() -> None:
    _, reported = variant_heading(
        _variant('c.98T>G', 'L33R', 'NM_004341.5:c.98T>G', 'p.Leu33Arg')
    )
    assert reported is None


def test_paper_nomenclature_shown_when_it_differs() -> None:
    # IFT74 Family 3: the paper's intronic deletion is not the one harmonized.
    title, reported = variant_heading(
        _variant('c.305+1664delG', None, 'NM_025103.4:c.306-1437del', None)
    )
    assert title == 'NM_025103.4:c.306-1437del'
    assert reported == 'c.305+1664delG'


def test_a_typo_in_the_transcript_alone_is_not_a_difference() -> None:
    # The change is what the slide compares; the accession is the title's.
    _, reported = variant_heading(
        _variant('GNM_004341.3:c.98T>G', None, 'NM_004341.5:c.98T>G', None)
    )
    assert reported is None


def test_differing_protein_change_shown() -> None:
    title, reported = variant_heading(
        _variant('c.98T>G', 'p.Leu33Pro', 'NM_004341.5:c.98T>G', 'p.Leu33Arg')
    )
    assert title == 'NM_004341.5:c.98T>G (p.Leu33Arg)'
    assert reported == 'p.Leu33Pro'


def test_paper_protein_in_title_when_none_harmonized() -> None:
    title, reported = variant_heading(
        _variant('c.98T>G', 'p.Leu33Arg', 'NM_004341.5:c.98T>G', None)
    )
    assert title == 'NM_004341.5:c.98T>G (p.Leu33Arg)'
    assert reported is None


def test_unharmonized_variant_titled_with_the_paper_once() -> None:
    title, reported = variant_heading(
        _variant('c.98T>G', 'p.Leu33Arg', harmonized=False)
    )
    assert title == 'c.98T>G (p.Leu33Arg)'
    assert reported is None


def test_variant_without_hgvs_titled_with_the_papers_wording() -> None:
    variant = _variant(None, 'p.Leu33Arg', harmonized=False)
    variant.variant_evidence = {'value': 'Leu33Arg missense'}
    assert variant_heading(variant) == ('Leu33Arg missense', None)


def test_harmonized_without_c_names_the_papers_c() -> None:
    # A genomic-only harmonization: the paper's c. is information, not a repeat.
    variant = _variant('c.98T>G', None, harmonized=False)
    variant.harmonized_variant = HarmonizedVariantDB(
        hgvs_g='NC_000002.12:g.27217368T>G'
    )
    assert variant_heading(variant) == ('NC_000002.12:g.27217368T>G', 'c.98T>G')
