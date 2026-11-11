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
