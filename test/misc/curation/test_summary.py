import pytest

from lib.misc.curation.summary import format_af


@pytest.mark.parametrize(
    ('af', 'expected'),
    [
        # Below 5e-6, where five fixed decimals printed 0.00000.
        (0.0000018588304982037502, '0.000001858830'),
        (0.000254237288, '0.0002542373'),
        (0.0123456789, '0.01234568'),
        (0.5, '0.5000000'),
        (1.0, '1.000000'),
        (3.2e-9, '0.000000003200000'),
        (0.0, '0'),
    ],
)
def test_format_af_keeps_seven_significant_figures(af: float, expected: str) -> None:
    assert format_af(af) == expected


def test_format_af_never_uses_scientific_notation() -> None:
    assert 'e' not in format_af(1e-12)
