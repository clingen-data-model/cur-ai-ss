"""Segregation arithmetic per the ClinGen Gene-Disease Validity SOP v12
(pp. 29-36), and the genotype a family member's links give them."""

import pytest

from lib.agents.segregation_analysis_computed_agent import (
    lod_score,
    minimum_criteria,
    scoring_method,
)
from lib.models import PatientVariantOccurrenceDB
from lib.tasks.handlers import segregation_basis, segregation_genotype


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


def _link(
    *methods: str, patient_id: int = 1, variant_id: int = 10
) -> PatientVariantOccurrenceDB:
    return PatientVariantOccurrenceDB(
        patient_id=patient_id, variant_id=variant_id, testing_methods=list(methods)
    )


def test_genotype_is_per_segregating_variant() -> None:
    """Tested for one of a compound-het proband's variants and only inferred
    for the other is a tested carrier of the first only."""
    links = [_link('Sanger Sequencing', variant_id=10), _link(variant_id=20)]
    assert segregation_genotype(links, [10, 20]) == {
        '10': 'tested carrier',
        '20': 'untested carrier',
    }


def test_unknown_method_is_tested_and_no_link_is_no_result() -> None:
    assert segregation_genotype([_link('Unknown')], [10, 20]) == {
        '10': 'tested carrier',
        '20': 'no result',
    }


def test_a_link_to_a_non_segregating_variant_never_counts() -> None:
    assert segregation_genotype([_link('Sanger Sequencing', variant_id=99)], [10]) == {
        '10': 'no result'
    }


def test_basis_is_the_probands_variants_and_methods() -> None:
    links = [
        _link('Exome Sequencing', 'Sanger Sequencing', patient_id=1, variant_id=10),
        _link('Sanger Sequencing', patient_id=2, variant_id=10),
        _link('MLPA', patient_id=3, variant_id=99),
    ]
    basis = segregation_basis({1}, links)
    assert basis.variant_ids == [10]
    assert basis.methods == ['Exome Sequencing', 'Sanger Sequencing']
    assert basis.from_proband


def test_basis_falls_back_to_the_family_without_a_linked_proband() -> None:
    links = [
        _link('Sanger Sequencing', patient_id=2, variant_id=10),
        _link(patient_id=3, variant_id=10),
    ]
    basis = segregation_basis({1}, links)
    assert basis.variant_ids == [10]
    assert basis.methods == ['Sanger Sequencing']
    assert not basis.from_proband


@pytest.mark.parametrize(
    ('values', 'method'),
    [
        (['Dominant', 'Dominant', 'Unknown'], 'Dominant'),
        (['X-linked'], 'Dominant'),
        (['Semi-dominant'], 'Dominant'),
        (['Recessive', 'Unknown', 'Recessive'], 'Recessive'),
        (['Unknown', 'Unknown', 'Recessive'], None),
        (['Mitochondrial'], None),
        ([], None),
    ],
)
def test_scoring_method_gives_none_for_unknown_or_non_mendelian(
    values: list[str], method: str | None
) -> None:
    """Anything not dominant used to score as Recessive, Unknown included."""
    assert scoring_method(values)['scoring_method'] == method


def test_no_scoring_method_fails_the_minimum_instead_of_raising() -> None:
    assert not _meets(scoring_method=None, segregation_count=6, affected_count=6)
