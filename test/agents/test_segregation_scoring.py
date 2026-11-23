"""Segregation arithmetic per the ClinGen Gene-Disease Validity SOP v12
(pp. 29-36), and the genotype a family member's links give them."""

import pytest

from lib.agents.segregation_analysis_computed_agent import (
    lod_score,
    minimum_criteria,
    scoring_method,
    semidominant_model,
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
        (['X-linked'], 'X-linked'),
        (['Semi-dominant'], 'Semidominant'),
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


def test_x_linked_daughters_of_an_affected_father_add_nothing() -> None:
    """SOP v12 p. 31: base 1 for a daughter of an affected father.
    Grandfather -> two carrier daughters -> an affected son each."""
    assert (
        _lod(scoring_method='X-linked', segregation_count=4, certain_segregations=2)
        == 0.6
    )
    assert _lod(scoring_method='X-linked', segregation_count=4) == 1.2


def test_certain_segregations_apply_to_x_linked_only() -> None:
    assert (
        _lod(scoring_method='Dominant', segregation_count=4, certain_segregations=2)
        == 1.2
    )


def test_x_linked_minimum_counts_certain_segregations() -> None:
    assert _meets(scoring_method='X-linked', segregation_count=4)
    assert not _meets(scoring_method='X-linked', segregation_count=3)


def test_recessive_with_an_affected_parent_uses_half_for_both() -> None:
    """SOP v12 p. 32: one parent affected, the other a carrier."""
    assert (
        _lod(
            scoring_method='Recessive',
            affected_count=3,
            unaffected_count=1,
            affected_parent=True,
        )
        == 0.9
    )
    assert (
        _lod(scoring_method='Recessive', affected_count=3, unaffected_count=1) == 1.33
    )


def test_semidominant_must_be_resolved_before_the_minimum() -> None:
    assert not _meets(scoring_method='Semidominant', segregation_count=6)


def _semi(**kw) -> str:
    args = {
        'ad_segregation_count': 0,
        'ar_affected_count': 1,
        'ar_unaffected_count': 0,
        'ar_affected_parent': False,
        'has_unexplainable_non_segregations': False,
        **kw,
    }
    return semidominant_model(**args)['scoring_method']


def test_semidominant_sop_example_1_scores_as_recessive() -> None:
    """Appendix p. 65: 6 affected biallelic members, 2 AD segregations."""
    assert _semi(ad_segregation_count=2, ar_affected_count=6) == 'Recessive'


def test_semidominant_sop_example_2_scores_as_dominant() -> None:
    """Appendix p. 65: 5 AD segregations, 2 biallelic members."""
    assert _semi(ad_segregation_count=5, ar_affected_count=2) == 'Dominant'


def test_semidominant_takes_the_higher_lod_when_both_qualify() -> None:
    # AD 4 segregations = 1.2 vs AR 4 affected = 1.81;
    # AD 8 segregations = 2.41 vs AR 3 affected = 1.2.
    assert _semi(ad_segregation_count=4, ar_affected_count=4) == 'Recessive'
    assert _semi(ad_segregation_count=8, ar_affected_count=3) == 'Dominant'
