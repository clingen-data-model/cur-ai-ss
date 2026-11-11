"""clinvar_lookup keeps the variation ID of the record it read the
classification from, so the UI can link to that record."""

from typing import Any

import pytest

from lib.agents import variant_annotation_agent as agent


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return self._payload


class _Session:
    def __init__(self, ids: list[str], summary: dict[str, Any]) -> None:
        self.ids = ids
        self.summary = summary

    def get(self, url: str, **_: Any) -> _Response:
        if url.endswith('esearch.fcgi'):
            return _Response({'esearchresult': {'idlist': self.ids}})
        return _Response({'result': self.summary})


@pytest.fixture
def clinvar(monkeypatch):
    def install(ids: list[str], summary: dict[str, Any]) -> None:
        monkeypatch.setattr(
            agent, '_get_session_with_retries', lambda: _Session(ids, summary)
        )

    return install


def test_keeps_the_variation_id_of_the_record_it_read(clinvar):
    clinvar(
        ['55601', '99999'],
        {
            'uids': ['55601', '99999'],
            '55601': {
                'germline_classification': {
                    'description': 'Pathogenic',
                    'review_status': 'reviewed by expert panel',
                },
                'supporting_submissions': {'scv': ['a', 'b']},
            },
            '99999': {'germline_classification': {'description': 'Benign'}},
        },
    )

    result = agent.clinvar_lookup('rs80357906', None, None, None)

    assert result.clinvar_variation_id == '55601'
    assert result.pathogenicity == 'Pathogenic'
    assert result.stars == 3
    assert result.submissions == 2


def test_no_record_no_variation_id(clinvar):
    clinvar([], {})

    result = agent.clinvar_lookup('rs1', None, None, None)

    assert result.clinvar_variation_id is None
    assert result.pathogenicity is None


@pytest.mark.parametrize('caid', ['_:CA', 'SCV000804199', 'SUB7928387', ' '])
def test_malformed_caid_is_left_out_of_the_search(monkeypatch, caid):
    """ClinVar reads "_:CA" as the word CA and returns thousands of unrelated
    records; OR'd with the HGVS, the top one became the classification."""
    terms: list[str] = []

    class Session(_Session):
        def get(self, url: str, **kwargs: Any) -> _Response:
            if url.endswith('esearch.fcgi'):
                terms.append(kwargs['params']['term'])
            return super().get(url, **kwargs)

    monkeypatch.setattr(agent, '_get_session_with_retries', lambda: Session([], {}))

    result = agent.clinvar_lookup(None, caid, 'NC_000011.10:g.1dup', None)

    assert terms == ['NC_000011.10:g.1dup']
    assert result.caid is None


def test_only_malformed_ids_means_no_search(monkeypatch):
    monkeypatch.setattr(
        agent, '_get_session_with_retries', lambda: pytest.fail('searched')
    )

    result = agent.clinvar_lookup('rs', '_:CA', None, None)

    assert result.pathogenicity is None
