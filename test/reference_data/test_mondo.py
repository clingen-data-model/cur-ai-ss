import json
from pathlib import Path
from typing import Any

import pytest

from lib.reference_data import mondo


@pytest.fixture
def mondo_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> mondo.MondoIndex:
    path = tmp_path / 'mondo.json'
    path.write_text(json.dumps({'graphs': [{'nodes': _mondo_nodes()}]}))
    index = mondo.build_mondo_index(path)
    monkeypatch.setattr(mondo, '_mondo_index', index)
    return index


def test_direct_mondo_id_match(mondo_index: mondo.MondoIndex) -> None:
    result, ambiguities = mondo.deterministic_index_lookup(mondo_index, 'MONDO:0007947')

    assert not ambiguities
    assert result is not None
    assert result.mondo_id == 'MONDO:0007947'
    assert result.term == 'Marfan syndrome'
    assert result.match_type == 'direct_mondo_id'


def test_embedded_mondo_id_match(mondo_index: mondo.MondoIndex) -> None:
    result, ambiguities = mondo.deterministic_index_lookup(
        mondo_index, 'Marfan syndrome (MONDO:0007947)'
    )

    assert not ambiguities
    assert result is not None
    assert result.mondo_id == 'MONDO:0007947'
    assert result.match_type == 'direct_mondo_id'


def test_non_mondo_curie_does_not_match_mondo_id(
    mondo_index: mondo.MondoIndex,
) -> None:
    result, ambiguities = mondo.deterministic_index_lookup(mondo_index, 'OMIM:0007947')

    assert not ambiguities
    assert result is None


def test_primary_label_match(mondo_index: mondo.MondoIndex) -> None:
    result, ambiguities = mondo.deterministic_index_lookup(
        mondo_index, 'cystic fibrosis'
    )

    assert not ambiguities
    assert result is not None
    assert result.mondo_id == 'MONDO:0009061'
    assert result.match_type == 'primary_label'


def test_exact_synonym_match(mondo_index: mondo.MondoIndex) -> None:
    result, ambiguities = mondo.deterministic_index_lookup(
        mondo_index, "Marfan's syndrome"
    )

    assert not ambiguities
    assert result is not None
    assert result.mondo_id == 'MONDO:0007947'
    assert result.match_type == 'exact_synonym'


def test_related_synonym_match(mondo_index: mondo.MondoIndex) -> None:
    result, ambiguities = mondo.deterministic_index_lookup(
        mondo_index, 'limb-girdle muscular dystrophy type 2Q'
    )

    assert not ambiguities
    assert result is not None
    assert result.mondo_id == 'MONDO:0013390'
    assert result.match_type == 'related_synonym'


def test_node_level_xref_identifier_match(mondo_index: mondo.MondoIndex) -> None:
    result, ambiguities = mondo.deterministic_index_lookup(mondo_index, 'GARD:0016535')

    assert not ambiguities
    assert result is not None
    assert result.mondo_id == 'MONDO:0007947'
    assert result.match_type == 'xref'


def test_exact_mapping_identifier_match(mondo_index: mondo.MondoIndex) -> None:
    result, ambiguities = mondo.deterministic_index_lookup(mondo_index, 'Orphanet:558')

    assert not ambiguities
    assert result is not None
    assert result.mondo_id == 'MONDO:0007947'
    assert result.match_type == 'exact_mapping_id'


def test_embedded_external_identifier_match(mondo_index: mondo.MondoIndex) -> None:
    result, ambiguities = mondo.deterministic_index_lookup(
        mondo_index, 'Disease identifier Orphanet:558'
    )

    assert not ambiguities
    assert result is not None
    assert result.mondo_id == 'MONDO:0007947'
    assert result.match_type == 'exact_mapping_id'


def test_synonym_xrefs_are_not_identifier_matches(
    mondo_index: mondo.MondoIndex,
) -> None:
    result, ambiguities = mondo.deterministic_index_lookup(mondo_index, 'SYNPROV:001')

    assert not ambiguities
    assert result is None


def test_unique_abbreviation_match(mondo_index: mondo.MondoIndex) -> None:
    result, ambiguities = mondo.deterministic_index_lookup(mondo_index, 'CF')

    assert not ambiguities
    assert result is not None
    assert result.mondo_id == 'MONDO:0009061'
    assert result.match_type == 'abbreviation'


def test_ambiguous_abbreviation_returns_ambiguity(
    mondo_index: mondo.MondoIndex,
) -> None:
    result, ambiguities = mondo.deterministic_index_lookup(mondo_index, 'MFS')

    assert result is None
    assert len(ambiguities) == 1
    assert ambiguities[0]['match_type'] == 'abbreviation'
    assert len(ambiguities[0]['candidates']) == 2


def test_deprecated_term_replacement(mondo_index: mondo.MondoIndex) -> None:
    result, ambiguities = mondo.deterministic_index_lookup(
        mondo_index, 'mucoviscidosis old name'
    )

    assert not ambiguities
    assert result is not None
    assert result.mondo_id == 'MONDO:0009061'
    assert result.match_type == 'deprecated_replacement'


def test_cross_species_nodes_are_indexed(mondo_index: mondo.MondoIndex) -> None:
    result, ambiguities = mondo.deterministic_index_lookup(mondo_index, 'MONDO:1010544')

    assert not ambiguities
    assert result is not None
    assert result.mondo_id == 'MONDO:1010544'
    assert result.term == 'cystic fibrosis, pig'


def test_animal_word_human_disease_name_is_indexed(
    mondo_index: mondo.MondoIndex,
) -> None:
    result, ambiguities = mondo.deterministic_index_lookup(
        mondo_index, 'cat eye syndrome'
    )

    assert not ambiguities
    assert result is not None
    assert result.mondo_id == 'MONDO:0007276'
    assert result.match_type == 'primary_label'


def test_retrieve_mondo_candidates_ranks_rapidfuzz_matches(
    mondo_index: mondo.MondoIndex,
) -> None:
    candidates = mondo.retrieve_mondo_candidates(mondo_index, 'cystic fibroses')

    assert candidates
    assert candidates[0].mondo_id == 'MONDO:0009061'
    assert candidates[0].alias_type == 'primary_label'
    assert candidates[0].retrieval_source == 'rapidfuzz'
    assert candidates[0].rapidfuzz_score is not None


def test_invalid_candidate_strategy_returns_empty(
    mondo_index: mondo.MondoIndex,
) -> None:
    candidates = mondo.retrieve_mondo_candidates(
        mondo_index,
        'cystic fibrosis',
        strategy='unsupported',
    )

    assert candidates == []


def test_empty_candidate_query_returns_empty(mondo_index: mondo.MondoIndex) -> None:
    candidates = mondo.retrieve_mondo_candidates(mondo_index, '   ')

    assert candidates == []


def _node(
    mondo_id: str,
    label: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        'id': f'http://purl.obolibrary.org/obo/{mondo_id.replace(":", "_")}',
        'lbl': label,
        'type': 'CLASS',
        'meta': meta or {},
    }


def _mondo_nodes() -> list[dict[str, Any]]:
    return [
        _node(
            'MONDO:0007947',
            'Marfan syndrome',
            {
                'synonyms': [
                    {
                        'pred': 'hasExactSynonym',
                        'val': "Marfan's syndrome",
                    },
                    {
                        'pred': 'hasExactSynonym',
                        'synonymType': 'http://purl.obolibrary.org/obo/mondo#ABBREVIATION',
                        'val': 'MFS',
                    },
                    {
                        'pred': 'hasExactSynonym',
                        'val': 'Marfan syndrome provenance-only synonym',
                        'xrefs': ['SYNPROV:001'],
                    },
                ],
                'xrefs': [{'val': 'GARD:0016535'}],
                'basicPropertyValues': [
                    {
                        'pred': 'http://www.w3.org/2004/02/skos/core#exactMatch',
                        'val': 'http://www.orpha.net/ORDO/Orphanet_558',
                    }
                ],
            },
        ),
        _node(
            'MONDO:0009061',
            'cystic fibrosis',
            {
                'synonyms': [
                    {
                        'pred': 'hasExactSynonym',
                        'synonymType': 'http://purl.obolibrary.org/obo/mondo#ABBREVIATION',
                        'val': 'CF',
                    },
                    {
                        'pred': 'hasExactSynonym',
                        'val': 'mucoviscidosis',
                    },
                ]
            },
        ),
        _node(
            'MONDO:0013390',
            'autosomal recessive limb-girdle muscular dystrophy type 2Q',
            {
                'synonyms': [
                    {
                        'pred': 'hasRelatedSynonym',
                        'val': 'limb-girdle muscular dystrophy type 2Q',
                    }
                ]
            },
        ),
        _node(
            'MONDO:0007276',
            'cat eye syndrome',
        ),
        _node(
            'MONDO:9990001',
            'mitral fibroelastosis syndrome',
            {
                'synonyms': [
                    {
                        'pred': 'hasExactSynonym',
                        'synonymType': 'http://purl.obolibrary.org/obo/mondo#ABBREVIATION',
                        'val': 'MFS',
                    }
                ]
            },
        ),
        _node(
            'MONDO:9990002',
            'mucoviscidosis old name',
            {
                'deprecated': True,
                'basicPropertyValues': [
                    {
                        'pred': 'http://purl.obolibrary.org/obo/IAO_0100001',
                        'val': 'http://purl.obolibrary.org/obo/MONDO_0009061',
                    }
                ],
            },
        ),
        _node(
            'MONDO:1010544',
            'cystic fibrosis, pig',
            {
                'basicPropertyValues': [
                    {
                        'pred': 'https://w3id.org/semapv/vocab/crossSpeciesExactMatch',
                        'val': 'http://purl.obolibrary.org/obo/MONDO_0009061',
                    }
                ]
            },
        ),
    ]
