"""The ClinVar lookup hands the harmonization agent every name a record is
known by, so a paper's legacy residue numbering can be matched to it."""

import json
from pathlib import Path

from lib.agents.variant_harmonization_agent import (
    VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS,
    _clinvar_records,
)

FIXTURE = Path(__file__).parent / 'fixtures' / 'clinvar_esummary_14879.json'


def test_records_carry_aliases_protein_change_and_condition():
    """VCV14879 is Vastardis 1996's MSX1 variant (paper 80). The paper calls
    it Arg31Pro, counted within the homeodomain; ClinVar titles it
    p.Arg202Pro and keeps R31P as an alias. On 2026-09-30 the agent rejected
    this record because the codons differed, having never been shown the
    alias."""
    (record,) = _clinvar_records(json.loads(FIXTURE.read_text()))

    assert record == {
        'hgvs': 'NM_002448.3(MSX1):c.605G>C (p.Arg202Pro)',
        'caid': 'CA124423',
        'rsid': 'rs121913129',
        'protein_change': 'R202P',
        'aliases': ['R31P'],
        'condition': ['Tooth agenesis, selective, 1'],
        'classification': 'Pathogenic',
    }


def test_missing_fields_read_as_empty_not_errors():
    summary = {
        'result': {
            'uids': ['1'],
            '1': {'variation_set': [{'variation_name': 'X', 'variation_xrefs': []}]},
        }
    }

    (record,) = _clinvar_records(summary)

    assert record['aliases'] == []
    assert record['condition'] == []
    assert record['protein_change'] is None
    assert record['classification'] is None
    assert record['caid'] is None and record['rsid'] is None


def test_empty_reply_yields_no_records():
    assert _clinvar_records({}) == []
    assert _clinvar_records({'result': {'uids': []}}) == []


def test_state_4_tells_the_agent_to_read_the_aliases_before_rejecting():
    rules = VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS
    assert 'aliases or protein_change, it IS the variant' in rules
    assert 'A mismatched codon alone is not grounds for rejection' in rules
    assert (
        rules.index('Step 5C')
        < rules.index('aliases or protein_change')
        < rules.index('Case A')
    )
