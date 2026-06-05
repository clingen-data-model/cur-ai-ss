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
    assert "Marfan's syndrome" in marfan.synonyms
    assert 'GARD:0016535' in marfan.xrefs
    assert 'http://www.orpha.net/ORDO/Orphanet_558' in marfan.exact_matches
    assert mondo_index.xref_to_ids['gard:0016535'] == ['MONDO:0007947']
    assert mondo_index.xref_to_ids['orphanet:558'] == ['MONDO:0007947']
    assert mondo_index.parent_ids_by_id['MONDO:0007947'] == ['MONDO:0700096']
    assert set(mondo_index.child_ids_by_id['MONDO:0700096']) == {
        'MONDO:0007947',
        'MONDO:0009061',
    }
    assert 'MONDO:9990001' not in mondo_index.terms_by_id


def test_get_mondo_term_accepts_curie_underscore_and_iri(
    mondo_index: mondo.MondoIndex,
) -> None:
    assert mondo.get_mondo_term('MONDO:0007947')['label'] == 'Marfan syndrome'
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


def test_empty_search_query_returns_no_candidates(
    mondo_index: mondo.MondoIndex,
) -> None:
    assert mondo.search_mondo_terms('   ') == []


def test_get_mondo_terms_by_xref_uses_xrefs_and_exact_matches(
    mondo_index: mondo.MondoIndex,
) -> None:
    assert mondo.get_mondo_terms_by_xref('GARD:0016535')[0]['mondo_id'] == (
        'MONDO:0007947'
    )
    assert mondo.get_mondo_terms_by_xref('http://www.orpha.net/ORDO/Orphanet_558')[
        0
    ]['mondo_id'] == 'MONDO:0007947'


def test_get_mondo_related_terms_returns_parent_and_children(
    mondo_index: mondo.MondoIndex,
) -> None:
    assert mondo.get_mondo_related_terms('MONDO:0007947', 'parents')[0][
        'mondo_id'
    ] == 'MONDO:0700096'
    children = mondo.get_mondo_related_terms('MONDO:0700096', 'children')
    assert {child['mondo_id'] for child in children} == {
        'MONDO:0007947',
        'MONDO:0009061',
    }


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
                    {'pred': 'hasExactSynonym', 'val': "Marfan's syndrome"},
                    {'pred': 'hasExactSynonym', 'val': 'MFS'},
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
