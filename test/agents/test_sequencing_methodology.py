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
