"""The identifier rules of the patient extraction prompt."""

from lib.agents.patient_extraction_agent import PATIENT_EXTRACTION_AGENT_INSTRUCTIONS


def test_a_role_is_the_identifier_and_the_family_is_its_own_field():
    """#447 prefixed a role with the family when the paper had several, so
    "sister" would not name a person in each. The family is a field of its own
    and the interface shows it, so the identifier carries it no longer."""
    rules = PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
    assert 'told apart by family_identifier' in rules
    assert 'Family 2 sister' not in rules
    assert 'The family is never part of the identifier' in rules


def test_a_numbered_symbol_is_that_many_patients():
    """The describer reports a numeral inside a symbol as a sibling group with
    its count (#451); nothing turned the group into people, so three sisters
    stayed one row. Segregation needs each of them."""
    rules = PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
    assert 'A symbol holding a number is that many people' in rules
    assert '(III-3a, III-3b, III-3c)' in rules
    assert 'A symbol holding "n" is one patient' in rules


def test_a_pedigree_member_is_written_position_first_then_label():
    """Within one family, patients came out as "II-1", "Subject 4" and
    "brother" side by side. Curators asked for pedigree position first with
    the paper's label in parentheses; the ladder still picks the label, one
    rule writes it down, and the family stays in its own field."""
    rules = PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
    assert 'How the identifier is written, once rules 1-6 have found' in rules
    assert '"II-1 (Subject 1)", "I-1 (father)", "III-2 (P84)"' in rules
    assert 'when the position is all the paper gives ("II-3")' in rules
    assert "A person no pedigree places is written as the paper's label alone" in rules
    assert "none is written as the paper's label alone" in rules
    assert 'The family is never part of the identifier' in rules


def test_a_family_drawn_twice_is_one_family_named_from_the_fuller_drawing():
    """ALX3 (PMID 19409524) draws each family in full in one figure and again,
    without the grandparents, above its gel in another. Each description
    numbers from its own top row, so subject 4 was III-4 in one and II-4 in
    the other, and nothing joined them. Patient extraction sees both."""
    rules = PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
    assert 'A family drawn in two figures' in rules
    assert 'is one family, named from the\nfuller drawing' in rules
    assert 'which position in the other figure is theirs' in rules
