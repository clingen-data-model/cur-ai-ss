"""The annotation lookups: clinvar_lookup keeps the variation ID of the record
it read the classification from, so the UI can link to that record, and
SpliceAI comes from the SpliceAI Lookup when VEP has none."""

from typing import Any

import pytest
import requests

from lib.agents import variant_annotation_agent as agent
from lib.models.variant import AnnotatedVariant, HarmonizedVariant


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


# gnomAD: "Variant not found" is the only answer that leaves the frequency
# empty; anything else means gnomAD did not answer, and that fails the task.


class _GnomadResponse:
    def __init__(self, payload: Any = None, status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise requests.HTTPError(f'{self.status} Client Error')

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _gnomad_answers(monkeypatch, response: _GnomadResponse) -> None:
    class _PostSession:
        def post(self, url: str, **_: Any) -> _GnomadResponse:
            return response

    monkeypatch.setattr(agent, '_get_session_with_retries', lambda: _PostSession())


def test_gnomad_not_found_is_an_empty_frequency(monkeypatch):
    _gnomad_answers(
        monkeypatch,
        _GnomadResponse(
            {'errors': [{'message': 'Variant not found'}], 'data': {'variant': None}}
        ),
    )
    result = agent.gnomad_lookup('9-27011970-T-G')
    assert result.gnomad_top_level_af is None
    assert result.gnomad_an is None


def test_gnomad_answer_is_read(monkeypatch):
    _gnomad_answers(
        monkeypatch,
        _GnomadResponse(
            {
                'data': {
                    'variant': {'joint': {'ac': 10, 'an': 1579274, 'populations': []}}
                }
            }
        ),
    )
    result = agent.gnomad_lookup('9-27011970-T-G')
    assert result.gnomad_ac == 10
    assert result.gnomad_top_level_af == pytest.approx(10 / 1579274)


@pytest.mark.parametrize(
    'response',
    [
        # Under load gnomAD has answered ordinary variants with a 400.
        _GnomadResponse(status=400),
        _GnomadResponse(status=503),
        _GnomadResponse({'errors': [{'message': 'Rate limit exceeded'}]}),
        _GnomadResponse(ValueError('Expecting value')),
    ],
    ids=['http-400', 'http-503', 'other-graphql-error', 'unreadable-json'],
)
def test_gnomad_failure_raises(monkeypatch, response):
    _gnomad_answers(monkeypatch, response)
    with pytest.raises(agent.GnomadLookupError):
        agent.gnomad_lookup('9-27011970-T-G')


def test_gnomad_failure_fails_the_batch(monkeypatch):
    def fail(_coordinates: str) -> AnnotatedVariant:
        raise agent.GnomadLookupError('gnomAD lookup failed')

    monkeypatch.setattr(agent, 'gnomad_lookup', fail)
    monkeypatch.setattr(agent, 'clinvar_lookup', lambda *_: AnnotatedVariant())
    monkeypatch.setattr(agent, 'vep_lookup', lambda *_: AnnotatedVariant())
    hv = HarmonizedVariant(
        gnomad_style_coordinates='9-27011970-T-G', hgvs_c='NM_025103.4:c.789+2T>G'
    )
    with pytest.raises(agent.GnomadLookupError):
        agent.enrich_variants_batch([hv], 'IFT74')


def test_other_source_failure_still_soft(monkeypatch):
    def fail(*_: Any) -> AnnotatedVariant:
        raise RuntimeError('VEP down')

    monkeypatch.setattr(
        agent,
        'gnomad_lookup',
        lambda c: AnnotatedVariant(
            gnomad_style_coordinates=c, gnomad_an=2, gnomad_ac=1
        ),
    )
    monkeypatch.setattr(agent, 'clinvar_lookup', lambda *_: AnnotatedVariant())
    monkeypatch.setattr(agent, 'vep_lookup', fail)
    hv = HarmonizedVariant(
        gnomad_style_coordinates='9-27011970-T-G', hgvs_c='NM_025103.4:c.789+2T>G'
    )
    [result] = agent.enrich_variants_batch([hv], 'IFT74')
    assert result.gnomad_an == 2
