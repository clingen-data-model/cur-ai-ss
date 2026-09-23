from collections import defaultdict

import hpotk
import pytest

import lib.reference_data.hpo as hpo_module
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
    result = find_matching_hpo_terms(
        'abnormality of the skeletal system', term_lookup=mock_term_lookup
    )

    assert len(result) > 0
    assert result[0].id == 'HP:0000001'
    assert result[0].name == 'abnormality of the skeletal system'
    assert result[0].similarity_score == 100.0


def test_find_matching_hpo_terms_partial_match(
    mock_term_lookup: defaultdict[str, list[hpotk.model._term_id.DefaultTermId]],
) -> None:
    """Test that partial matches are found and ordered by similarity score."""
    result = find_matching_hpo_terms('skeletal problems', term_lookup=mock_term_lookup)

    assert len(result) > 2
    # Verify results are ordered by similarity score (descending)
    scores = [r.similarity_score for r in result]
    assert scores == sorted(scores, reverse=True)

    # Verify specific term matches and score ranges
    assert result[0].id == 'HP:0000001'
    assert int(result[0].similarity_score) == 59

    assert result[2].id == 'HP:0000004'
    assert int(result[2].similarity_score) == 44

    # Scores should be different between top and third match
    assert result[0].similarity_score > result[2].similarity_score


def test_find_matching_hpo_terms_case_insensitive(
    mock_term_lookup: defaultdict[str, list[hpotk.model._term_id.DefaultTermId]],
) -> None:
    """Test that matching is case-insensitive."""
    result_lower = find_matching_hpo_terms(
        'intellectual disability', term_lookup=mock_term_lookup
    )
    result_upper = find_matching_hpo_terms(
        'INTELLECTUAL DISABILITY', term_lookup=mock_term_lookup
    )
    result_mixed = find_matching_hpo_terms(
        'InTeLLeCtUaL dIsAbIlItY', term_lookup=mock_term_lookup
    )

    assert result_lower[0].id == result_upper[0].id
    assert result_lower[0].id == result_mixed[0].id


def test_find_matching_hpo_terms_limit(
    mock_term_lookup: defaultdict[str, list[hpotk.model._term_id.DefaultTermId]],
) -> None:
    """Test that the limit parameter is respected."""
    result_limit_2 = find_matching_hpo_terms(
        'abnormal', term_lookup=mock_term_lookup, limit=2
    )
    result_limit_5 = find_matching_hpo_terms(
        'abnormal', term_lookup=mock_term_lookup, limit=5
    )

    assert len(result_limit_2) <= 2
    assert len(result_limit_5) <= 5


def test_find_matching_hpo_terms_result_structure(
    mock_term_lookup: defaultdict[str, list[hpotk.model._term_id.DefaultTermId]],
) -> None:
    """Test that results have the expected structure."""
    result = find_matching_hpo_terms(
        'cardiac abnormality', term_lookup=mock_term_lookup
    )

    assert isinstance(result, list)
    assert len(result) > 0

    for item in result:
        assert hasattr(item, 'id')
        assert hasattr(item, 'name')
        assert hasattr(item, 'similarity_score')
        assert isinstance(item.id, str)
        assert isinstance(item.name, str)
        assert isinstance(item.similarity_score, float)
        assert 0 <= item.similarity_score <= 100


def test_get_term_lookup_builds_once_and_caches(monkeypatch) -> None:
    """The whole point of the cache: /hpo/search shouldn't rebuild the
    ~19k-term lookup on every keystroke, and the HPO linking agent's tool
    loop shouldn't rebuild it on every search_hpo_terms call either."""
    monkeypatch.setattr(hpo_module, '_term_lookup', None)
    build_calls = []
    fake_lookup: defaultdict[str, list[hpotk.model._term_id.DefaultTermId]] = (
        defaultdict(list, {'seizures': [hpotk.TermId.from_curie('HP:0000005')]})
    )

    def fake_build() -> defaultdict[str, list[hpotk.model._term_id.DefaultTermId]]:
        build_calls.append(1)
        return fake_lookup

    monkeypatch.setattr(hpo_module, 'build_term_lookup', fake_build)

    first = hpo_module.get_term_lookup()
    second = hpo_module.get_term_lookup()

    assert first is second is fake_lookup
    assert len(build_calls) == 1


def test_find_matching_hpo_terms_uses_the_cached_lookup_by_default(monkeypatch) -> None:
    """Calling without a term_lookup (as every real caller does) should go
    through the cache rather than building fresh each time."""
    monkeypatch.setattr(hpo_module, '_term_lookup', None)
    build_calls = []
    fake_lookup: defaultdict[str, list[hpotk.model._term_id.DefaultTermId]] = (
        defaultdict(list, {'seizures': [hpotk.TermId.from_curie('HP:0000005')]})
    )

    def fake_build() -> defaultdict[str, list[hpotk.model._term_id.DefaultTermId]]:
        build_calls.append(1)
        return fake_lookup

    monkeypatch.setattr(hpo_module, 'build_term_lookup', fake_build)

    hpo_module.find_matching_hpo_terms('seizures')
    hpo_module.find_matching_hpo_terms('seizures')

    assert len(build_calls) == 1


def test_warm_term_lookup_if_cached_skips_when_ontology_file_is_absent(
    monkeypatch, tmp_path
) -> None:
    """A cold CAA_ROOT (every test run, a brand-new deployment) must never
    trigger a network download at startup -- warming should no-op and leave
    the lazy build-on-first-use path for get_term_lookup() to handle."""
    monkeypatch.setattr(hpo_module, '_term_lookup', None)
    monkeypatch.setattr(hpo_module, 'ontology_path', lambda: tmp_path / 'missing.json')

    def fail_if_called() -> defaultdict[str, list[hpotk.model._term_id.DefaultTermId]]:
        raise AssertionError(
            'build_term_lookup should not run when the ontology is not cached'
        )

    monkeypatch.setattr(hpo_module, 'build_term_lookup', fail_if_called)

    hpo_module.warm_term_lookup_if_cached()

    assert hpo_module._term_lookup is None


def test_warm_term_lookup_if_cached_builds_when_ontology_file_is_present(
    monkeypatch, tmp_path
) -> None:
    """Once the ontology is already on disk, warming should build the lookup
    eagerly so the first real search request doesn't pay for it."""
    monkeypatch.setattr(hpo_module, '_term_lookup', None)
    cached_path = tmp_path / 'hp.json'
    cached_path.write_text('{}')
    monkeypatch.setattr(hpo_module, 'ontology_path', lambda: cached_path)

    fake_lookup: defaultdict[str, list[hpotk.model._term_id.DefaultTermId]] = (
        defaultdict(list, {'seizures': [hpotk.TermId.from_curie('HP:0000005')]})
    )
    monkeypatch.setattr(hpo_module, 'build_term_lookup', lambda: fake_lookup)

    hpo_module.warm_term_lookup_if_cached()

    assert hpo_module._term_lookup is fake_lookup


def test_find_matching_hpo_terms_synonym_match(
    mock_term_lookup: defaultdict[str, list[hpotk.model._term_id.DefaultTermId]],
) -> None:
    """Test that synonyms are matched."""
    # 'skeletal abnormality' is a synonym for the same term as 'abnormality of the skeletal system'
    result = find_matching_hpo_terms(
        'skeletal abnormality', term_lookup=mock_term_lookup
    )

    assert len(result) > 0
    # Should match with high score due to being in lookup
    assert result[0].similarity_score >= 95
