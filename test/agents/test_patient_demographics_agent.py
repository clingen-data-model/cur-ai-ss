"""The demographics prompt's affected-status rule for relatives."""

from lib.agents.patient_demographics_agent import (
    PATIENT_DEMOGRAPHICS_AGENT_INSTRUCTIONS,
)


def test_a_relative_in_the_positive_family_history_is_affected():
    """Paper 111 (TUBA4A, FTD-ALS): "Familial history was positive", then a
    mother who died of reported AD and an aunt and grandmother with memory
    problems. One run marked all three Affected, the next left two Unknown,
    because "the condition" could be read as ALS alone. The rule now says the
    paper's own family history decides, and the same way for every member."""
    rules = PATIENT_DEMOGRAPHICS_AGENT_INSTRUCTIONS
    affected = rules[
        rules.index('- affected_status') : rules.index('- is_obligate_carrier')
    ]
    assert 'counts in a positive family history' in affected
    assert 'an illness the paper does not relate' in affected
    assert 'Read every member of the family by the same rule' in affected
