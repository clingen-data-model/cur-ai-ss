"""The evidence contract every extraction prompt carries speaks in citations."""

import pytest

from lib.agents.core_extraction_rules import CORE_EXTRACTION_SPEC
from lib.agents.manual_output import _JSON_OUTPUT_DIRECTIVE
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


def test_spec_tells_the_agent_to_cite_a_header_cell_through_the_table_id():
    assert 'The header row has no id of its own' in CORE_EXTRACTION_SPEC
    assert '"Pat. 1 *"' in CORE_EXTRACTION_SPEC
    assert 'Never cite a data row for text that appears only in the header' in (
        CORE_EXTRACTION_SPEC.replace('\n  ', ' ')
    )


def test_patient_extraction_covers_patient_labels_in_a_header_row():
    text = PATIENT_EXTRACTION_AGENT_INSTRUCTIONS

    assert 'one patient per column' in text
    assert 'the quote is "Pat. 1 *"' in text


def test_spec_no_longer_asks_for_the_legacy_fields():
    assert '0-based' not in CORE_EXTRACTION_SPEC
    assert 'Count only tables' not in CORE_EXTRACTION_SPEC
    assert 'quote, table_id, or image_id' not in CORE_EXTRACTION_SPEC
    assert 'is_supplement: boolean' not in CORE_EXTRACTION_SPEC


def test_manual_output_directive_speaks_in_citations():
    rendered = _JSON_OUTPUT_DIRECTIVE.format(schema='{}')

    assert 'citations MUST hold at least one {"anchor", "quote"}' in rendered
    assert 'legacy' not in rendered
    assert 'table_id' not in rendered


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


def test_phenotype_prompt_tells_the_agent_what_to_do_for_an_unaffected_patient():
    """Paper 45: eight unaffected relatives were given the family's hearing loss
    ("assumed to be an affected member") because the agent never saw their status."""
    prompt = PATIENT_PHENOTYPE_LINKING_AGENT_INSTRUCTIONS
    assert 'affected_status' in prompt
    assert 'Unaffected' in prompt
    assert 'assumed to be' in prompt  # named as the forbidden reasoning
    # Attribution decides, not status: a stated finding is extracted regardless.
    assert 'never overrides what the text says' in prompt
    assert 'extract it anyway' in prompt


def test_variant_prompt_keeps_literature_variants_and_labels_them_not_main_focus():
    """Papers 45, 56, 68 and 70 lost their previously reported variants: the paper's
    own are main focus, the others are kept with main_focus false."""
    prompt = VARIANT_EXTRACTION_AGENT_INSTRUCTIONS
    assert 'Extract EVERY variant of the target gene' in prompt
    assert 'Never leave a variant out' in prompt
    assert 'set main_focus to false' in prompt


def test_patient_prompt_uses_pedigree_labels_even_for_a_single_case_report():
    """Papers 53 and 68 named the patient "patient" and dropped the labeled
    relatives although the pedigree labels them (II-2, II-1)."""
    prompt = PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
    assert 'use the pedigree label' in prompt
    assert 'this rule does not\n   apply' in prompt
    assert 'including a single case report' in prompt


def test_patient_prompt_names_the_three_haiku_misses():
    """With claude-haiku-5-5 on identical code: paper 53 dropped the "Lam et al."
    comparison column and (once) the role-named parents, paper 65 dropped P21's
    father and mother although each transmitted an allele, and paper 76 returned
    the bare table cells "1"/"2A" where the text says "Individual 5"."""
    prompt = PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
    assert 'headed by the citation' in prompt
    assert 'is a label for that individual, not an author mention' in prompt
    assert 'The single-case rule names the proband only' in prompt
    assert 'an allele traced to one parent' in prompt
    assert 'never\n       the identifier by itself' in prompt
    assert 'use that one form\n       for every member of the series' in prompt
    assert 'BEFORE RETURNING, CHECK:' in prompt


def test_patient_prompt_makes_candidate_enumeration_a_step():
    """Haiku 5.5 on paper 53 omitted the "Lam et al." column at medium, high and
    max effort alike, then agreed it qualified the moment a follow-up pointed at
    it: it never listed the column as a candidate. The procedure makes listing
    come before deciding."""
    prompt = PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
    assert 'PROCEDURE -- work in this order' in prompt
    assert '1. Enumerate candidates.' in prompt
    assert 'every row label and every column header in every table' in prompt
    assert '2. Decide each candidate.' in prompt
    assert prompt.index('1. Enumerate candidates.') < prompt.index(
        'Identifier priority rules'
    )


def test_patient_prompt_examples_are_not_lifted_from_the_eval_papers():
    """The misses were found on papers 53, 65 and 76; an example copied from one
    of them verbatim teaches the model that paper, not the rule."""
    prompt = PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
    for verbatim in (
        'Lam et al',
        'Indiv ID',
        'Individual 1',
        'P21',
        'inherited from her father',
        'analyzed using WES',
        'TOP2B',
        'COG4',
        'FOXE3',
    ):
        assert verbatim not in prompt, verbatim


def test_spec_disambiguates_a_cell_that_repeats_across_a_table_row():
    """A matrix table (one column per patient) repeats "+" or "Severe" across a row;
    a bare quote of that cell cannot say whose it is."""
    assert 'carries only a flag' in CORE_EXTRACTION_SPEC
    assert 'each row is a patient' in CORE_EXTRACTION_SPEC
    assert (
        'never quote only the row' in CORE_EXTRACTION_SPEC.replace('\n  ', ' ').lower()
    )
    assert '"Hypotonia | + | +"' in CORE_EXTRACTION_SPEC
    assert 'Never quote a flag or repeated cell bare' in CORE_EXTRACTION_SPEC
