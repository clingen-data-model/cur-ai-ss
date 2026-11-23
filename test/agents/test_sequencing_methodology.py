"""Every testing method maps to a sequencing methodology, so a method added to
the list cannot silently fall through to Unknown in segregation scoring."""

from lib.agents.segregation_analysis_computed_agent import _TESTING_TO_METHODOLOGY
from lib.models.patient_variant_occurrences import TestingMethod
from lib.models.segregation_analysis import SequencingMethodology


def test_every_testing_method_has_a_methodology():
    assert set(_TESTING_TO_METHODOLOGY) == {m.value for m in TestingMethod}


def test_mlpa_is_a_candidate_gene_method():
    assert (
        _TESTING_TO_METHODOLOGY[TestingMethod.mlpa.value]
        == SequencingMethodology.CandidateGene.value
    )


def test_methodology_is_the_probands_broadest_method():
    """SOP v12 p. 35: the proband's exome counts even when relatives were
    confirmed by Sanger or tested by an unnamed method."""
    from lib.agents.segregation_analysis_computed_agent import sequencing_methodology

    def pick(*methods: str) -> str:
        return sequencing_methodology(list(methods))['sequencing_methodology']

    assert (
        pick(
            TestingMethod.exome_sequencing.value, TestingMethod.sanger_sequencing.value
        )
        == SequencingMethodology.ExomeOrGenome.value
    )
    assert (
        pick(
            TestingMethod.linkage_analysis.value, TestingMethod.sanger_sequencing.value
        )
        == SequencingMethodology.AllGenesInRegion.value
    )
    assert (
        pick(TestingMethod.sanger_sequencing.value)
        == SequencingMethodology.CandidateGene.value
    )
    assert pick() == SequencingMethodology.Unknown.value
