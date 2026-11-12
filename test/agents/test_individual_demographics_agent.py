"""The demographics prompt's affected-status rule for relatives."""

from lib.agents.individual_demographics_agent import (
    INDIVIDUAL_DEMOGRAPHICS_AGENT_INSTRUCTIONS,
)


def test_a_relative_in_the_positive_family_history_is_affected():
    """Paper 111 (TUBA4A, FTD-ALS): "Familial history was positive", then a
    mother who died of reported AD and an aunt and grandmother with memory
    problems. One run marked all three Affected, the next left two Unknown,
    because "the condition" could be read as ALS alone. The rule now says the
    paper's own family history decides, and the same way for every member."""
    rules = INDIVIDUAL_DEMOGRAPHICS_AGENT_INSTRUCTIONS
    affected = rules[
        rules.index('- affected_status') : rules.index('- is_obligate_carrier')
    ]
    assert 'counts in a positive family history' in affected
    assert 'an illness the paper does not relate' in affected
    assert 'Read every member of the family by the same rule' in affected


def test_report_age_is_the_latest_age_the_paper_gives():
    """A patient described at two ages came out at the younger one; the age at
    report cannot be an age the paper has already moved past."""
    rules = INDIVIDUAL_DEMOGRAPHICS_AGENT_INSTRUCTIONS
    assert 'age_report is the oldest age the paper gives' in rules


def test_identifiers_are_read_within_the_patients_family():
    """Paper 160's three unnumbered pedigrees each had a II-1; told only the
    identifier, the agent flagged 113 of them as matching several pedigrees
    and wrote the wrong pedigree's sex and status for others."""
    from lib.agents.individual_demographics_agent import (
        INDIVIDUAL_DEMOGRAPHICS_AGENT_INSTRUCTIONS as rules,
    )
    from lib.agents.patient_phenotype_linking_agent import (
        PATIENT_PHENOTYPE_LINKING_AGENT_INSTRUCTIONS as phenotype_rules,
    )

    assert 'An identifier is unique only within its family' in rules
    assert 'named by family_identifier' in rules
    assert "family_identifier (the patient's family" in phenotype_rules
