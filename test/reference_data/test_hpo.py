from collections import defaultdict

import hpotk
import pytest

from lib.reference_data.hpo import find_matching_hpo_terms


@pytest.fixture
def mock_term_lookup() -> defaultdict[str, list[hpotk.model._term_id.DefaultTermId]]:
    """Create a mock term lookup for testing."""
    lookup = defaultdict(list)
    # Create mock HPO term IDs
    term_id_1 = hpotk.TermId.from_curie('HP:0000001')
    term_id_2 = hpotk.TermId.from_curie('HP:0000002')
    term_id_3 = hpotk.TermId.from_curie('HP:0000003')
    term_id_4 = hpotk.TermId.from_curie('HP:0000004')
    term_id_5 = hpotk.TermId.from_curie('HP:0000005')

    lookup['abnormality of the skeletal system'] = [term_id_1]
    lookup['skeletal abnormality'] = [term_id_1]  # synonym
    lookup['abnormal heart'] = [term_id_2]
    lookup['cardiac abnormality'] = [term_id_2]  # synonym
    lookup['intellectual disability'] = [term_id_3]
    lookup['developmental delay'] = [term_id_4]
    lookup['seizures'] = [term_id_5]

    return lookup


def test_find_matching_hpo_terms_exact_match(
    mock_term_lookup: defaultdict[str, list[hpotk.model._term_id.DefaultTermId]],
) -> None:
    """Test that exact matches are found with high similarity score."""
    result = find_matching_hpo_terms('abnormality of the skeletal system', mock_term_lookup)

    assert len(result) > 0
    assert result[0].hpo_id == 'HP:0000001'
    assert result[0].hpo_name == 'abnormality of the skeletal system'
    assert result[0].similarity_score == 100.0


def test_find_matching_hpo_terms_partial_match(
    mock_term_lookup: defaultdict[str, list[hpotk.model._term_id.DefaultTermId]],
) -> None:
    """Test that partial matches are found and ordered by similarity score."""
    result = find_matching_hpo_terms('skeletal problems', mock_term_lookup)

    assert len(result) > 2
    # Verify results are ordered by similarity score (descending)
    scores = [r.similarity_score for r in result]
    assert scores == sorted(scores, reverse=True)

    # Verify specific term matches and score ranges
    assert result[0].hpo_id == 'HP:0000001'
    assert result[0].similarity_score == 64.0

    assert result[2].hpo_id == 'HP:0000003'
    assert result[2].similarity_score == 45.0

    # Scores should be different between top and third match
    assert result[0].similarity_score > result[2].similarity_score


def test_find_matching_hpo_terms_case_insensitive(
    mock_term_lookup: defaultdict[str, list[hpotk.model._term_id.DefaultTermId]],
) -> None:
    """Test that matching is case-insensitive."""
    result_lower = find_matching_hpo_terms(
        'intellectual disability', mock_term_lookup
    )
    result_upper = find_matching_hpo_terms(
        'INTELLECTUAL DISABILITY', mock_term_lookup
    )
    result_mixed = find_matching_hpo_terms(
        'InTeLLeCtUaL dIsAbIlItY', mock_term_lookup
    )

    assert result_lower[0].hpo_id == result_upper[0].hpo_id
    assert result_lower[0].hpo_id == result_mixed[0].hpo_id


def test_find_matching_hpo_terms_limit(
    mock_term_lookup: defaultdict[str, list[hpotk.model._term_id.DefaultTermId]],
) -> None:
    """Test that the limit parameter is respected."""
    result_limit_2 = find_matching_hpo_terms('abnormal', mock_term_lookup, limit=2)
    result_limit_5 = find_matching_hpo_terms('abnormal', mock_term_lookup, limit=5)

    assert len(result_limit_2) <= 2
    assert len(result_limit_5) <= 5


def test_find_matching_hpo_terms_result_structure(
    mock_term_lookup: defaultdict[str, list[hpotk.model._term_id.DefaultTermId]],
) -> None:
    """Test that results have the expected structure."""
    result = find_matching_hpo_terms('cardiac abnormality', mock_term_lookup)

    assert isinstance(result, list)
    assert len(result) > 0

    for item in result:
        assert hasattr(item, 'hpo_id')
        assert hasattr(item, 'hpo_name')
        assert hasattr(item, 'similarity_score')
        assert isinstance(item.hpo_id, str)
        assert isinstance(item.hpo_name, str)
        assert isinstance(item.similarity_score, float)
        assert 0 <= item.similarity_score <= 100


def test_find_matching_hpo_terms_synonym_match(
    mock_term_lookup: defaultdict[str, list[hpotk.model._term_id.DefaultTermId]],
) -> None:
    """Test that synonyms are matched."""
    # 'skeletal abnormality' is a synonym for the same term as 'abnormality of the skeletal system'
    result = find_matching_hpo_terms('skeletal abnormality', mock_term_lookup)

    assert len(result) > 0
    # Should match with high score due to being in lookup
    assert result[0].similarity_score >= 95
