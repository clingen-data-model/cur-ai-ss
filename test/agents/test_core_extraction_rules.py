"""The evidence contract every extraction prompt carries speaks in citations."""

import pytest

from lib.agents.core_extraction_rules import CORE_EXTRACTION_SPEC
from lib.agents.paper_extraction_agent import PAPER_EXTRACTION_AGENT_INSTRUCTIONS
from lib.agents.patient_demographics_agent import (
    PATIENT_DEMOGRAPHICS_AGENT_INSTRUCTIONS,
)
from lib.agents.patient_extraction_agent import PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
from lib.agents.patient_phenotype_linking_agent import (
    PATIENT_PHENOTYPE_LINKING_AGENT_INSTRUCTIONS,
)
from lib.agents.patient_variant_occurrence_agent import (
    PATIENT_VARIANT_OCCURRENCE_AGENT_INSTRUCTIONS,
)
from lib.agents.segregation_evidence_extractor import (
    SEGREGATION_EVIDENCE_AGENT_INSTRUCTIONS,
)
from lib.agents.variant_extraction_agent import VARIANT_EXTRACTION_AGENT_INSTRUCTIONS


def test_spec_names_every_id_form_and_the_shortest_span_rule():
    for form in ('[paragraph-N]', '[table-N]', 'table-N-row-R', '[figure-N]', 'supp-'):
        assert form in CORE_EXTRACTION_SPEC
    assert 'shortest verbatim span' in CORE_EXTRACTION_SPEC
    assert '{"anchor", "quote"}' in CORE_EXTRACTION_SPEC  # not a leftover {{ }}
    assert 'EXTRACTION WARNING' in CORE_EXTRACTION_SPEC


def test_spec_no_longer_asks_for_the_legacy_fields():
    assert '0-based' not in CORE_EXTRACTION_SPEC
    assert 'Count only tables' not in CORE_EXTRACTION_SPEC
    assert 'quote, table_id, or image_id' not in CORE_EXTRACTION_SPEC
    assert 'is_supplement: boolean' not in CORE_EXTRACTION_SPEC


@pytest.mark.parametrize(
    'instructions',
    [
        PAPER_EXTRACTION_AGENT_INSTRUCTIONS,
        PATIENT_EXTRACTION_AGENT_INSTRUCTIONS,
        PATIENT_DEMOGRAPHICS_AGENT_INSTRUCTIONS,
        VARIANT_EXTRACTION_AGENT_INSTRUCTIONS,
        PATIENT_VARIANT_OCCURRENCE_AGENT_INSTRUCTIONS,
        PATIENT_PHENOTYPE_LINKING_AGENT_INSTRUCTIONS,
        SEGREGATION_EVIDENCE_AGENT_INSTRUCTIONS,
    ],
)
def test_every_evidence_producing_prompt_asks_for_citations(instructions):
    assert 'citations' in instructions
    assert (
        '{{' not in instructions
    )  # an f-string escape that leaked into a plain string
    for legacy in (
        'At least one of quote, table_id, or image_id',
        'table or figure number',
        'image_id: integer index',
        'legacy',
        'table_id',
    ):
        assert legacy not in instructions
