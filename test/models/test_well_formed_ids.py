"""Only ClinGen Allele Registry IDs are stored as CAIDs."""

import pytest

from lib.models.converters import harmonized_variant_to_db
from lib.models.evidence_block import ReasoningBlock
from lib.models.variant import HarmonizedVariant, well_formed_caid, well_formed_rsid


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        ('CA117961', 'CA117961'),
        (' CA117961 ', 'CA117961'),
        ('_:CA', None),
        ('SCV000804199', None),
        ('SUB7928387', None),
        ('CA', None),
        ('', None),
        (None, None),
    ],
)
def test_well_formed_caid(value, expected):
    assert well_formed_caid(value) == expected


@pytest.mark.parametrize(
    ('value', 'expected'),
    [('rs80357906', 'rs80357906'), ('rs', None), ('80357906', None), (None, None)],
)
def test_well_formed_rsid(value, expected):
    assert well_formed_rsid(value) == expected


def test_harmonized_row_drops_a_placeholder_caid():
    row = harmonized_variant_to_db(
        1,
        ReasoningBlock[HarmonizedVariant](
            value=HarmonizedVariant(caid='_:CA', rsid='rs1'), reasoning='r'
        ),
    )
    assert row.caid is None
    assert row.rsid == 'rs1'
