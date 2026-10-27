"""The extraction prompt's rules for notation older papers use.

Paper 109 (PKD1, PMID 11012875) writes every variant as "C6058T" with the
residue beside it as "S1949S" and names "L33234 for PKD1 cDNA positions". The
first run wrote none of the silent changes into hgvs_p and dropped the
accession, so harmonization had nothing to search on and nothing to tell it
the numbering was not RefSeq c. numbering.
"""

from lib.agents.variant_extraction_agent import VARIANT_EXTRACTION_AGENT_INSTRUCTIONS


def test_a_silent_change_becomes_a_synonymous_hgvs_p():
    rules = VARIANT_EXTRACTION_AGENT_INSTRUCTIONS
    assert 'p.Ser120=, p.Thr45=' in rules
    assert '"S120S" is p.Ser120= by the same fixed' in rules
    allowed = rules[rules.index('ALLOWED inference') : rules.index('DISALLOWED')]
    assert 'A silent change is no exception' in allowed


def test_a_genbank_cdna_reference_is_kept_as_the_transcript():
    rules = VARIANT_EXTRACTION_AGENT_INSTRUCTIONS
    assert '"X12345 for cDNA' in rules
    assert rules.index('X12345') < rules.index('protein_accession → NP_')


def test_nucleotide_changes_are_still_not_turned_into_hgvs_c():
    """The number, not the format, is what is wrong in such papers; a c. string
    stamped by extraction would only make the wrong position look authoritative."""
    assert (
        'Nucleotide changes without coordinate system'
        in VARIANT_EXTRACTION_AGENT_INSTRUCTIONS
    )
