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


def test_state_0_checks_the_paper_position_against_the_residue_window():
    """Paper 109 (PKD1, 2000) numbers from the L33243 mRNA start, 211 ahead of
    HGVS c.; 'C7696T' projected cleanly onto Leu2566 and was stored as a real
    allele. The window check is what catches that before projection."""
    rules = VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS
    assert 'residue N is encoded by c.(3N-2) to c.3N' in rules
    assert '"C810T" with "R200X" does not' in rules
    assert rules.index('Numbering check') < rules.index('STATE 1')


def test_state_3_projects_the_window_candidates_and_vetoes_a_wrong_consequence():
    rules = VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS
    state_3 = rules[rules.index('STATE 3') : rules.index('STATE 4')]
    assert 'gives c.598C>T, c.599C>T and' in state_3
    assert 'Consequence check' in state_3
    assert 'a Synonymous input that resolved' in state_3
    assert 'Do not return it with a note' in state_3
    assert state_3.index('Numbering.') < state_3.index('1. Resolve')
    assert state_3.index('Call allele_registry_resolver') < state_3.index(
        'Consequence check'
    )


def test_a_genbank_transcript_sends_the_agent_to_the_canonical_one():
    rules = VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS
    assert 'is a GenBank accession rather' in rules
    assert 'counted from an mRNA start' in rules  # and it is not a conflict flag


def test_an_uncheckable_position_on_a_genbank_sequence_is_not_projected():
    """The first run of the rule projected paper 109's 'Del 1 bp (G3336)' as
    c.3336del: no residue to check, so the mRNA-start number went through and
    resolved a frameshift the paper never describes."""
    rules = VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS
    assert 'is not projected at all' in rules
    assert 'other than the one the paper names' in rules
