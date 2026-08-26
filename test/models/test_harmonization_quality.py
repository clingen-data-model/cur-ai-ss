"""Harmonization quality predicates behind the variant tab's ⚠️ marker.

The examples are taken verbatim from harmonized rows in the curation database,
so a regression here is a regression against real papers.
"""

from lib.models.variant import HarmonizedVariant, is_harmonized, malformed_identifiers


def test_is_harmonized_requires_a_lookup_identifier() -> None:
    assert is_harmonized(HarmonizedVariant(hgvs_c='NM_004341.5:c.98T>G'))
    assert is_harmonized(HarmonizedVariant(rsid='rs429358'))
    assert is_harmonized(HarmonizedVariant(gnomad_style_coordinates='19-44908684-T-C'))


def test_is_harmonized_rejects_empty_and_protein_only() -> None:
    assert not is_harmonized(None)
    assert not is_harmonized(HarmonizedVariant())
    # A protein change alone cannot be annotated, which is why the worker skips
    # these rows -- so the UI must flag them too.
    assert not is_harmonized(HarmonizedVariant(hgvs_p='p.Gln214Arg'))


def test_well_formed_identifiers_are_not_flagged() -> None:
    assert (
        malformed_identifiers(
            HarmonizedVariant(
                gnomad_style_coordinates='19-44908684-T-C',
                rsid='rs429358',
                hgvs_c='NM_004341.5:c.5365C>T',
                hgvs_g='NC_000008.11:g.106945267G>A',
                hgvs_p='p.(Gln214Arg)',
            )
        )
        == {}
    )
    # Non-substitution changes name their operator instead of ">".
    for hgvs_c in (
        'NM_004341.5:c.100_101del',
        'NM_004341.5:c.100dup',
        'NM_004341.5:c.100_101insA',
        'NM_004341.5:c.100_200inv',
        'NM_004341.5:c.100=',
    ):
        assert malformed_identifiers(HarmonizedVariant(hgvs_c=hgvs_c)) == {}


def test_flags_hgvs_with_no_change_operator() -> None:
    # Legacy notation: reference base before the position, not HGVS.
    assert malformed_identifiers(HarmonizedVariant(hgvs_c='NM_012082.4:c.C2665G')) == {
        'hgvs_c': 'NM_012082.4:c.C2665G'
    }


def test_flags_identifiers_containing_whitespace() -> None:
    # ">" read as "4" out of a mangled table cell, space and all.
    assert malformed_identifiers(
        HarmonizedVariant(hgvs_c='NM_004341.5:c.1843-3C 4T')
    ) == {'hgvs_c': 'NM_004341.5:c.1843-3C 4T'}
    # Control characters count as whitespace too.
    assert malformed_identifiers(HarmonizedVariant(hgvs_p='p.Lys303Serfs \x1f 28')) == {
        'hgvs_p': 'p.Lys303Serfs \x1f 28'
    }


def test_reports_every_malformed_field_at_once() -> None:
    assert malformed_identifiers(
        HarmonizedVariant(
            hgvs_c='NM_012082.4:c.A679G',
            hgvs_g='NC_000007.14:g.103354482_105407628x1',
        )
    ) == {
        'hgvs_c': 'NM_012082.4:c.A679G',
        'hgvs_g': 'NC_000007.14:g.103354482_105407628x1',
    }


def test_nothing_to_check_when_unharmonized() -> None:
    assert malformed_identifiers(None) == {}
    assert malformed_identifiers(HarmonizedVariant()) == {}
