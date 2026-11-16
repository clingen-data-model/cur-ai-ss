"""The annotation lookups: clinvar_lookup keeps the variation ID of the record
it read the classification from, so the UI can link to that record, and
SpliceAI comes from the SpliceAI Lookup when VEP has none."""

from typing import Any

import pytest

from lib.agents import variant_annotation_agent as agent
from lib.models.variant import AnnotatedVariant, SpliceAI


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


# --- SpliceAI Lookup fallback -------------------------------------------------

# The Lookup's answer for IFT74 c.789+2T>G (chr9-27011970-T-G), trimmed to one
# MANE Select and one other IFT74 transcript plus a neighbouring gene; delta
# scores come back as strings.
_LOOKUP_IFT74 = {
    'variant': 'chr9-27011970-T-G',
    'source': 'spliceai:model',
    'scores': [
        {
            'g_name': 'OTHER',
            't_priority': 'MS',
            'DS_AG': '0.999',
            'DS_AL': '0.000',
            'DS_DG': '0.000',
            'DS_DL': '0.000',
            'DP_AG': 1,
            'DP_AL': 1,
            'DP_DG': 1,
            'DP_DL': 1,
        },
        {
            'g_name': 'IFT74',
            't_priority': 'N',
            'DS_AG': '0.004',
            'DS_AL': '0.000',
            'DS_DG': '0.302',
            'DS_DL': '0.500',
            'DP_AG': 152,
            'DP_AL': -64,
            'DP_DG': 162,
            'DP_DL': -2,
        },
        {
            'g_name': 'IFT74',
            't_priority': 'MS',
            'DS_AG': '0.004',
            'DS_AL': '0.000',
            'DS_DG': '0.302',
            'DS_DL': '0.998',
            'DP_AG': 152,
            'DP_AL': -64,
            'DP_DG': 162,
            'DP_DL': -2,
        },
    ],
}


def _lookup_session(monkeypatch, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Answers every GET with payload and records the params it was sent."""
    calls: list[dict[str, Any]] = []

    class Session:
        def get(self, url: str, **kwargs: Any) -> _Response:
            calls.append({'url': url, **kwargs.get('params', {})})
            return _Response(payload)

    monkeypatch.setattr(agent, '_get_session_with_retries', Session)
    return calls


def test_lookup_reads_the_curated_genes_mane_transcript(monkeypatch):
    calls = _lookup_session(monkeypatch, _LOOKUP_IFT74)

    result = agent.spliceai_lookup('9-27011970-T-G', 'IFT74')

    assert result is not None
    assert result.max_score == pytest.approx(0.998)
    assert result.effect_type == 'DS_DL'
    assert result.position == -2
    # Same 50 bp window as VEP's precomputed scores, chr-prefixed coordinates.
    assert calls[0]['variant'] == 'chr9-27011970-T-G'
    assert calls[0]['distance'] == 50


def test_lookup_error_or_no_scores_is_none(monkeypatch):
    _lookup_session(monkeypatch, {'error': 'unable to parse variant'})
    assert agent.spliceai_lookup('9-1-A-AT', 'IFT74') is None

    _lookup_session(monkeypatch, {'scores': []})
    assert agent.spliceai_lookup('9-1-A-T', 'IFT74') is None


def test_lookup_failure_is_none(monkeypatch):
    class Session:
        def get(self, url: str, **_: Any) -> _Response:
            raise agent.requests.exceptions.ConnectionError('refused')

    monkeypatch.setattr(agent, '_get_session_with_retries', Session)

    assert agent.spliceai_lookup('9-27011970-T-G', 'IFT74') is None


def _vep(spliceai: dict[str, Any] | None) -> list[dict[str, Any]]:
    """A VEP answer for the IFT74 variant, with or without a SpliceAI score."""
    tx: dict[str, Any] = {
        'gene_symbol': 'IFT74',
        'mane_select': 'NM_025103.4',
        'impact': 'HIGH',
        'consequence_terms': ['splice_donor_variant'],
    }
    if spliceai is not None:
        tx['spliceai'] = spliceai
    return [{'transcript_consequences': [tx]}]


def _vep_session(monkeypatch, answer: Any) -> list[str]:
    """VEP gives answer (an exception is raised); records the coordinates the
    Lookup is asked for."""
    asked: list[str] = []

    class Session:
        def get(self, url: str, **_: Any) -> _Response:
            if isinstance(answer, Exception):
                raise answer
            return _Response(answer)

    def lookup(coords: str, gene: str) -> SpliceAI:
        asked.append(coords)
        return SpliceAI(max_score=0.998, effect_type='DS_DL', position=-2)

    monkeypatch.setattr(agent, '_get_session_with_retries', Session)
    monkeypatch.setattr(agent, 'spliceai_lookup', lookup)
    return asked


def _vep_lookup() -> AnnotatedVariant:
    return agent.vep_lookup(
        None, 'NC_000009.12:g.27011970T>G', None, 'IFT74', '9-27011970-T-G'
    )


def test_vep_answer_without_spliceai_asks_the_lookup(monkeypatch):
    asked = _vep_session(monkeypatch, _vep(None))

    result = _vep_lookup()

    assert asked == ['9-27011970-T-G']
    assert result.spliceai is not None
    assert result.spliceai.max_score == pytest.approx(0.998)
    assert result.vep_consequence == 'splice_donor_variant'


def test_vep_spliceai_is_kept_without_asking_the_lookup(monkeypatch):
    asked = _vep_session(
        monkeypatch, _vep({'DS_AG': 0.95, 'DS_AL': 0.97, 'DP_AG': 8, 'DP_AL': 2})
    )

    result = _vep_lookup()

    assert asked == []
    assert result.spliceai is not None
    assert result.spliceai.effect_type == 'DS_AL'


def test_vep_failure_does_not_ask_the_lookup(monkeypatch):
    """Only a VEP answer lacking SpliceAI sends a variant to the Lookup, whose
    public API is rate-limited; a VEP error leaves SpliceAI empty."""
    asked = _vep_session(
        monkeypatch, agent.requests.exceptions.ConnectionError('refused')
    )

    result = _vep_lookup()

    assert asked == []
    assert result.spliceai is None


def test_no_coordinates_no_lookup(monkeypatch):
    asked = _vep_session(monkeypatch, _vep(None))

    result = agent.vep_lookup(None, 'NC_000009.12:g.27011970T>G', None, 'IFT74')

    assert asked == []
    assert result.spliceai is None


def test_from_raw_reads_string_scores():
    result = SpliceAI.from_raw({'DS_AG': '0.004', 'DS_DL': '0.998', 'DP_DL': -2})

    assert result.max_score == pytest.approx(0.998)
    assert result.effect_type == 'DS_DL'
    assert result.position == -2
