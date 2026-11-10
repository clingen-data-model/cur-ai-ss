import pytest

from lib.misc.curation.summary import format_af


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
