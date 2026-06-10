import json
from pathlib import Path
from typing import Any

import pytest

from lib.reference_data import mondo


@pytest.fixture
def mondo_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> mondo.MondoIndex:
    path = tmp_path / 'mondo.json'
    path.write_text(
        json.dumps(
            {
                'graphs': [
                    {
                        'nodes': _mondo_nodes(),
                        'edges': [
                            {
                                'sub': _iri('MONDO:0007947'),
                                'pred': 'is_a',
                                'obj': _iri('MONDO:0700096'),
                            },
                            {
                                'sub': _iri('MONDO:0009061'),
                                'pred': 'is_a',
                                'obj': _iri('MONDO:0700096'),
                            },
                        ],
                    }
                ]
            }
        )
    )
    index = mondo.build_mondo_index(path)
    monkeypatch.setattr(mondo, '_mondo_index', index)
    return index


def test_index_builds_tool_oriented_structures(
    mondo_index: mondo.MondoIndex,
) -> None:
    marfan = mondo_index.terms_by_id['MONDO:0007947']

    assert marfan.label == 'Marfan syndrome'
    assert marfan.definition == 'A connective tissue disorder.'
    assert any(
        synonym.text == "Marfan's syndrome" and synonym.scope == 'exact'
        for synonym in marfan.synonyms
    )
    assert any(
        synonym.text == 'MFS'
        and synonym.scope == 'exact'
        and synonym.synonym_type == 'ABBREVIATION'
        for synonym in marfan.synonyms
    )
    assert 'GARD:0016535' in marfan.xrefs
    assert 'http://www.orpha.net/ORDO/Orphanet_558' in marfan.exact_matches
    assert mondo_index.identifier_to_ids['mondo:0007947'] == ['MONDO:0007947']
    assert mondo_index.identifier_to_ids['gard:0016535'] == ['MONDO:0007947']
    assert mondo_index.identifier_to_ids['orphanet:558'] == ['MONDO:0007947']
    assert any(
        alias.mondo_id == 'MONDO:0007947'
        and alias.text == 'MFS'
        and alias.type == 'synonym'
        and alias.synonym_scope == 'exact'
        and alias.synonym_type == 'ABBREVIATION'
        for alias in mondo_index.search_aliases
    )
    assert mondo_index.parent_ids_by_id['MONDO:0007947'] == ['MONDO:0700096']
    assert set(mondo_index.child_ids_by_id['MONDO:0700096']) == {
        'MONDO:0007947',
        'MONDO:0009061',
    }
    assert 'MONDO:9990001' not in mondo_index.terms_by_id


def test_get_mondo_term_accepts_curie_underscore_and_iri(
    mondo_index: mondo.MondoIndex,
) -> None:
    term = mondo.get_mondo_term('MONDO:0007947')

    assert term['label'] == 'Marfan syndrome'
    assert {(synonym['text'], synonym['scope']) for synonym in term['synonyms']} >= {
        ("Marfan's syndrome", 'exact'),
        ('connective tissue disorder', 'related'),
    }
    assert term['parents'] == [{'mondo_id': 'MONDO:0700096', 'label': 'human disease'}]
    assert term['children'] == []
    assert mondo.get_mondo_term('MONDO_0007947')['label'] == 'Marfan syndrome'
    assert mondo.get_mondo_term(_iri('MONDO:0007947'))['label'] == 'Marfan syndrome'
    assert mondo.get_mondo_term('OMIM:154700') is None


def test_search_mondo_terms_returns_near_matches(
    mondo_index: mondo.MondoIndex,
) -> None:
    candidates = mondo.search_mondo_terms('cystic fibroses')

    assert candidates
    assert candidates[0]['mondo_id'] == 'MONDO:0009061'
    assert candidates[0]['label'] == 'cystic fibrosis'
    assert candidates[0]['score'] > 80
    assert candidates[0]['matches'][0]['text'] == 'cystic fibrosis'
    assert candidates[0]['matches'][0]['normalized_text'] == 'cystic fibrosis'
    assert candidates[0]['matches'][0]['type'] == 'label'


def test_search_mondo_terms_returns_synonym_evidence(
    mondo_index: mondo.MondoIndex,
) -> None:
    candidates = mondo.search_mondo_terms('mucoviscidosis')

    assert candidates[0]['mondo_id'] == 'MONDO:0009061'
    assert candidates[0]['matches'][0]['text'] == 'mucoviscidosis'
    assert candidates[0]['matches'][0]['type'] == 'synonym'
    assert candidates[0]['matches'][0]['synonym_scope'] == 'exact'


def test_search_mondo_terms_groups_multiple_match_evidence(
    mondo_index: mondo.MondoIndex,
) -> None:
    candidates = mondo.search_mondo_terms('Marfan syndrome')

    marfan = next(
        candidate
        for candidate in candidates
        if candidate['mondo_id'] == 'MONDO:0007947'
    )
    assert {
        (match['text'], match['type'], match.get('synonym_scope'))
        for match in marfan['matches']
    } >= {
        ('Marfan syndrome', 'label', None),
        ('Marfan syndrome', 'synonym', 'exact'),
    }


def test_empty_search_query_returns_no_candidates(
    mondo_index: mondo.MondoIndex,
) -> None:
    assert mondo.search_mondo_terms('   ') == []


def test_get_mondo_by_identifier_uses_mondo_ids_xrefs_and_exact_matches(
    mondo_index: mondo.MondoIndex,
) -> None:
    assert mondo.get_mondo_by_identifier('MONDO_0007947')[0]['mondo_id'] == (
        'MONDO:0007947'
    )
    assert mondo.get_mondo_by_identifier('GARD:0016535')[0]['mondo_id'] == (
        'MONDO:0007947'
    )
    assert mondo.get_mondo_by_identifier('ORPHA:558')[0]['mondo_id'] == (
        'MONDO:0007947'
    )
    assert (
        mondo.get_mondo_by_identifier('http://www.orpha.net/ORDO/Orphanet_558')[0][
            'mondo_id'
        ]
        == 'MONDO:0007947'
    )


def test_get_mondo_parents_and_children_return_related_terms(
    mondo_index: mondo.MondoIndex,
) -> None:
    assert mondo.get_mondo_parents('MONDO:0007947')[0]['mondo_id'] == 'MONDO:0700096'
    children = mondo.get_mondo_children('MONDO:0700096')
    assert {child['mondo_id'] for child in children} == {
        'MONDO:0007947',
        'MONDO:0009061',
    }
    assert children[0]['parents'] == []
    assert children[0]['children'] == []


def test_mondo_agent_message_includes_scoped_target() -> None:
    from lib.agents.mondo_linking_agent import build_mondo_agent_message

    target = mondo.MondoLinkingTarget(
        scope=mondo.MondoDiseaseScope.OCCURRENCE,
        paper_id=123,
        patient_variant_occurrence_id=456,
        disease_text='Marfan syndrome (MONDO:0007947)',
        context=mondo.MondoDiseaseContext(
            gene_symbol='FBN1',
            occurrence_disease_text='Marfan syndrome (MONDO:0007947)',
        ),
    )

    message = build_mondo_agent_message(target)

    payload = json.loads(
        message.removeprefix('MONDO linking target JSON:\n').split('\n\n', 1)[0]
    )
    assert payload['scope'] == 'occurrence'
    assert payload['patient_variant_occurrence_id'] == 456
    assert payload['disease_text'] == 'Marfan syndrome (MONDO:0007947)'
    assert payload['context']['gene_symbol'] == 'FBN1'


def _iri(mondo_id: str) -> str:
    return f'http://purl.obolibrary.org/obo/{mondo_id.replace(":", "_")}'


def _node(
    mondo_id: str,
    label: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        'id': _iri(mondo_id),
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
                'definition': {'val': 'A connective tissue disorder.'},
                'synonyms': [
                    {'pred': 'hasExactSynonym', 'val': 'Marfan syndrome'},
                    {'pred': 'hasExactSynonym', 'val': "Marfan's syndrome"},
                    {
                        'pred': 'hasExactSynonym',
                        'val': 'MFS',
                        'synonymType': 'http://purl.obolibrary.org/obo/mondo#ABBREVIATION',
                    },
                    {
                        'pred': 'hasRelatedSynonym',
                        'val': 'connective tissue disorder',
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
                    {'pred': 'hasExactSynonym', 'val': 'mucoviscidosis'},
                    {'pred': 'hasExactSynonym', 'val': 'CF'},
                ],
                'xrefs': [{'val': 'OMIM:219700'}],
            },
        ),
        _node('MONDO:0700096', 'human disease'),
        _node(
            'MONDO:9990001',
            'deprecated disease',
            {'deprecated': True},
        ),
    ]
