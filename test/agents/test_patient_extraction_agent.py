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


def test_a_numbered_symbol_is_that_many_patients():
    """The describer reports a numeral inside a symbol as a sibling group with
    its count (#451); nothing turned the group into people, so three sisters
    stayed one row. Segregation needs each of them."""
    rules = PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
    assert 'A symbol holding a number is that many people' in rules
    assert '(III-3a, III-3b, III-3c)' in rules
    assert 'A symbol holding "n" is one patient' in rules


def test_a_pedigree_member_is_written_family_first_then_position_then_label():
    """Within one family, patients came out as "II-1", "Subject 4" and
    "brother" side by side. Curators asked for pedigree position first with
    the paper's label in parentheses; the ladder still picks the label, one
    rule writes it down."""
    rules = PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
    assert 'How the identifier is written, once rules 1-6 have found' in rules
    assert '"Family 1 II-1 (Subject 1)"' in rules
    assert (
        'left off when the position is all the paper gives ("Family 1 II-3")' in rules
    )
    assert "A person no pedigree places is written as the paper's label alone" in rules
    assert "none is written as the paper's label alone" in rules
