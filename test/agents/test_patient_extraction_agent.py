"""The identifier rules of the patient extraction prompt."""

from lib.agents.patient_extraction_agent import PATIENT_EXTRACTION_AGENT_INSTRUCTIONS


def test_a_relative_is_named_by_their_proband_when_the_paper_has_several():
    """A two-family paper that named nobody came out as "index patient",
    "brother", "father", "mother": the bare role, right for a one-proband
    paper, named a person in each family here."""
    rules = PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
    assert 'while the paper\n       has one proband' in rules
    assert 'qualified by the proband it belongs to' in rules
    assert '"sister of Patient 2", "father of the index patient"' in rules
