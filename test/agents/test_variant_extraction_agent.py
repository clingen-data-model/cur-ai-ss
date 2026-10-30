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
    allowed = rules[rules.index('ALLOWED inference') : rules.index('DISALLOWED')]
    assert '"S120S", "Thr45Thr" (silent) → p.Ser120=, p.Thr45=' in allowed


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


def test_stop_lost_is_a_variant_type_told_apart_from_stop_gained():
    """A read-through variant was classed as stop gained or unknown for want of
    a label; the enum, the prompt's label list and its rule now carry it."""
    from lib.models.variant import VariantType

    assert VariantType('Stop Lost') is VariantType.stop_lost
    rules = VARIANT_EXTRACTION_AGENT_INSTRUCTIONS
    types = rules[
        rules.index('VARIANT TYPE CLASSIFICATION') : rules.index('VARIANT-LEVEL')
    ]
    assert '- stop lost\n' in types
    assert 'the opposite of stop gained' in types


def test_a_frameshift_is_labelled_by_its_nucleotide_change():
    """c.517_521dup (MAG, PMID 32629324) was labelled Frameshift because the paper
    said "frameshift", with the dup in hand to say insertion."""
    rules = VARIANT_EXTRACTION_AGENT_INSTRUCTIONS
    assert 'dup or ins is\n  frameshift insertion, del is frameshift deletion' in rules
    assert 'Plain frameshift only when the paper gives no change' in rules


def test_the_functional_evidence_basis_states_results_not_only_methods():
    """The curation export prints this basis as the paper's functional
    summary, and a basis asked only how the evidence was determined listed
    the assays without their outcomes."""
    rules = VARIANT_EXTRACTION_AGENT_INSTRUCTIONS
    assert 'what the studies found, not only that they were done' in rules
    assert "Curators read this as the paper's functional summary" in rules
