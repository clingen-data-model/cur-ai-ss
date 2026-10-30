"""The identifier rules of the patient extraction prompt."""

from lib.agents.patient_extraction_agent import PATIENT_EXTRACTION_AGENT_INSTRUCTIONS


def test_a_relative_is_named_by_their_family_when_the_paper_has_several():
    """A two-family paper that named nobody came out as "index patient",
    "brother", "father", "mother": the bare role, right for a one-proband
    paper, named a person in each family here."""
    rules = PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
    assert 'while the paper\n       has one family' in rules
    assert 'prefixed with the family identifier assigned below' in rules
    assert '"Family 2 sister", "Family A father"' in rules
