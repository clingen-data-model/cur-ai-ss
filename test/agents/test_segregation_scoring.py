"""Segregation arithmetic per the ClinGen Gene-Disease Validity SOP v12
(pp. 29-36), and the genotype a family member's links give them."""

import pytest

from lib.agents.segregation_analysis_computed_agent import lod_score, minimum_criteria
from lib.models import PatientVariantOccurrenceDB
from lib.tasks.handlers import segregation_genotype


def _lod(**kw) -> float:
    args = {
        'segregation_count': 0,
        'affected_count': 0,
        'unaffected_count': 0,
        'extracted_lod_score': None,
        **kw,
    }
    return lod_score(**args)['lod_score']


def test_dominant_lod_matches_the_sop_table() -> None:
    # Figure 4: 4 segregations 1.2, 10 segregations 3.0.
    assert _lod(scoring_method='Dominant', segregation_count=4) == 1.2
    assert _lod(scoring_method='Dominant', segregation_count=10) == 3.01


def test_recessive_lod_counts_the_proband_among_the_affected() -> None:
    """A proband and one affected sibling is 0.25^1, LOD 0.6; it was 0.0
    when the proband was left out of the count and subtracted again."""
    assert _lod(scoring_method='Recessive', affected_count=2) == 0.6
    assert (
        _lod(scoring_method='Recessive', affected_count=3, unaffected_count=1) == 1.33
    )
    assert _lod(scoring_method='Recessive', affected_count=1) == 0.0


def test_a_published_lod_is_used_as_given() -> None:
    assert (
        _lod(scoring_method='Recessive', affected_count=3, extracted_lod_score=3.2)
        == 3.2
    )


def _meets(**kw) -> bool:
    args = {
        'segregation_count': 0,
        'affected_count': 0,
        'has_unexplainable_non_segregations': False,
        'extracted_lod_score': None,
        **kw,
    }
    return minimum_criteria(**args)['meets_criteria']


@pytest.mark.parametrize(
    ('affected', 'meets'), [(2, False), (3, True)], ids=['two', 'three']
)
def test_recessive_minimum_is_three_affected_including_the_proband(
    affected: int, meets: bool
) -> None:
    assert _meets(scoring_method='Recessive', affected_count=affected) is meets


def test_dominant_minimum_is_four_segregations() -> None:
    assert not _meets(scoring_method='Dominant', segregation_count=3)
    assert _meets(scoring_method='Dominant', segregation_count=4)


def test_a_published_lod_is_not_held_to_the_size_minimums() -> None:
    assert _meets(
        scoring_method='Dominant', segregation_count=2, extracted_lod_score=3.2
    )
    assert _meets(scoring_method='Recessive', affected_count=2, extracted_lod_score=3.2)


def test_an_unexplainable_non_segregation_fails_even_a_published_lod() -> None:
    assert not _meets(
        scoring_method='Dominant',
        segregation_count=6,
        extracted_lod_score=3.2,
        has_unexplainable_non_segregations=True,
    )


def _link(*methods: str) -> PatientVariantOccurrenceDB:
    return PatientVariantOccurrenceDB(testing_methods=list(methods))


def test_genotype_is_tested_when_a_link_names_a_method() -> None:
    assert segregation_genotype([_link('Sanger Sequencing')]) == 'tested carrier'
    assert segregation_genotype([_link(), _link('Genotyping')]) == 'tested carrier'


def test_genotype_is_untested_when_no_link_names_a_method() -> None:
    assert segregation_genotype([_link()]) == 'untested carrier'


def test_genotype_is_no_result_without_a_link() -> None:
    assert segregation_genotype([]) == 'no result'
