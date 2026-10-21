"""The evidence contract every extraction prompt carries speaks in citations."""

import pytest

from lib.agents.compound_het_agent import COMPOUND_HET_AGENT_INSTRUCTIONS
from lib.agents.core_extraction_rules import CORE_EXTRACTION_SPEC, FLAG_RULES
from lib.agents.hpo_linking_agent import HPO_LINKING_AGENT_INSTRUCTIONS
from lib.agents.manual_output import _JSON_OUTPUT_DIRECTIVE
from lib.agents.mondo_linking_agent import MONDO_LINKING_AGENT_INSTRUCTIONS
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
from lib.agents.segregation_analysis_computed_agent import (
    SEGREGATION_ANALYSIS_COMPUTED_AGENT_INSTRUCTIONS,
)
from lib.agents.segregation_evidence_extractor import (
    SEGREGATION_EVIDENCE_AGENT_INSTRUCTIONS,
)
from lib.agents.variant_extraction_agent import VARIANT_EXTRACTION_AGENT_INSTRUCTIONS
from lib.agents.variant_harmonization_agent import (
    VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS,
)
from lib.models.flag import FlagKind


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
    assert 'is a label for that\n   individual, not an author mention' in prompt
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
    # The list has to land somewhere the model is obliged to write: an existing
    # free-text field. Haiku went from 0/20 to 6/9 on the citation-headed
    # column once the list had a home; a bare "list before deciding" did nothing.
    assert 'written out in full in the reasoning of the\nfirst family' in prompt
    assert 'lists every candidate label with\n  its decision' in prompt


def test_patient_prompt_extracts_every_pedigree_symbol_and_role_named_relative():
    """The prompt used to skip pedigree members the paper prints no label for
    and relatives the text names collectively ("the parents"): seven of the
    ten PATIENT_EXTRACTION exclusion flags on dev were exactly those people,
    genotyped parents and untested siblings included -- the individuals
    segregation evidence is built from. Every symbol is now a patient, married-in
    spouses included, with an "inferred" flag in place of the old "excluded"
    one. The describer's positional label is the last resort, used if and only
    if the paper names the person nowhere: a role in the text ("the proband's
    father") is a label the paper gives and always wins over "I-1"."""
    prompt = PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
    assert 'A person needs no printed label to count' in prompt
    assert 'labeled or not, affected or not, blood relative or married in' in prompt
    assert '5. Only when the paper names a person nowhere' in prompt
    assert 'a positional label never stands in for a label the paper gives' in prompt
    assert 'Only a symbol the paper names nowhere\ntakes the positional label' in (
        prompt
    )
    assert '"the\n     parents" of one proband are a mother and a father' in prompt
    assert 'A relative is never excluded for lacking a label' in prompt
    assert 'Every individual the pedigree description lists has a patient' in prompt
    # The old rule, in all three of the places it was stated.
    assert 'no label is invented' not in prompt.lower()
    assert "those labels are the describer's, not the paper's" not in prompt
    assert 'assigned by position as no\nlabel at all' not in prompt


def test_patient_prompt_scopes_to_the_target_gene_and_fills_the_schema():
    """A 19-disease exome cohort came back as 33 patients, one per diagnosed
    member, under a prompt that never mentioned the gene it was handed. The
    same pass removed rules the output schema cannot honour: a bare "unknown"
    return, an "Other" proband status, nullable fields, a nullable
    consanguinity, and two proband rules that disagreed (most fully described
    member vs "has no proband") so that one family could end up with none.
    The one family allowed none is spelled out as an exception (see the
    re-reported test below), not left to two rules fighting."""
    prompt = PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
    assert 'SCOPE -- the target gene' in prompt
    assert 'only reported finding is in another gene is out of' in prompt
    assert 'Every family the paper reports for the first time has exactly one' in (
        prompt
    )
    assert prompt.count('has no proband') == 1
    assert 'False also means "not\n  stated"' in prompt
    assert 'return empty "patients" and\n   "families" lists' in prompt
    assert 'return "unknown"' not in prompt
    assert '"Other" or "Unknown"' not in prompt
    assert 'returned as null' not in prompt


def test_patient_prompt_never_makes_a_re_reported_individual_the_proband():
    """Once every family had to have a proband, a previously published patient
    the paper carries as its own table column, and a boy from the discussion
    whose parents are the evidence, each became the proband of a singleton
    family: three papers over-counted the unrelated probands curators score
    by one each. Curation counts the probands a paper adds."""
    prompt = PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
    assert 'is never the\n  proband here' in prompt
    assert 'the one exception to\n  the one-proband rule' in prompt
    assert 'no re-reported individual is one' in prompt


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


def test_spec_states_the_flag_rule_once_for_every_agent():
    """Scoping and the one-proband rule make decisions a curator cannot see from
    the output: a cohort member left out, a relative mentioned once and
    dropped, a proband chosen where the paper marks none. Field reasoning only
    covers what was extracted, so the shared spec asks every agent for a flag
    per decision, and each prompt adds only its own examples."""
    assert FLAG_RULES in CORE_EXTRACTION_SPEC
    assert 'FLAGS -- decisions a curator should see' in FLAG_RULES
    # The two things a value's reasoning cannot carry, now as kinds: what a
    # rule kept out, and a call the paper leaves open.
    assert 'a rule here kept out of\n    your output' in CORE_EXTRACTION_SPEC
    assert 'a call the paper itself leaves open' in CORE_EXTRACTION_SPEC
    # Output in its uncertain form beats nothing: a curator deletes in one
    # click and adds by hand.
    assert 'Prefer output a curator can review over nothing' in FLAG_RULES
    assert 'Leave something out only when' in FLAG_RULES
    assert 'Do not flag routine extraction' in CORE_EXTRACTION_SPEC
    assert 'one flag per decision, not per item it touches' in CORE_EXTRACTION_SPEC
    assert 'null when it\n    is about something not extracted' in CORE_EXTRACTION_SPEC
    # The lookup agents have no citations field; the rule says so once.
    assert 'where the block has citations' in FLAG_RULES
    # The bar, after the first local run raised 184 flags on three papers:
    # most were "not stated", rule-required Unknowns and canonical choices.
    assert 'Never flag:' in FLAG_RULES
    assert 'a field the paper does not state' in FLAG_RULES
    assert 'a value a rule here required' in FLAG_RULES
    assert 'as good as the inputs allow' in FLAG_RULES
    assert 'your own process' in FLAG_RULES
    assert 'Most runs raise none or a few' in FLAG_RULES
    # The closed list, after the second run still raised 70: a flag is one of
    # six kinds or it is not a flag, and a decision an upstream task made is
    # not flagged again downstream.
    assert (
        'Every flag is of one kind, and a decision that fits no kind is not a flag'
        in (FLAG_RULES)
    )
    for kind in FlagKind:
        assert f'  - {kind.value}: ' in FLAG_RULES
    assert 'Flag only decisions your own output makes' in FLAG_RULES
    assert 'kind: one of the kinds above' in FLAG_RULES
    # The old template asked for a counterfactual on every flag, and got one.
    assert 'what a curator might decide instead' not in FLAG_RULES


@pytest.mark.parametrize(
    'instructions',
    [
        PATIENT_EXTRACTION_AGENT_INSTRUCTIONS,
        PATIENT_DEMOGRAPHICS_AGENT_INSTRUCTIONS,
        VARIANT_EXTRACTION_AGENT_INSTRUCTIONS,
        PATIENT_VARIANT_OCCURRENCE_AGENT_INSTRUCTIONS,
        PATIENT_PHENOTYPE_LINKING_AGENT_INSTRUCTIONS,
        SEGREGATION_EVIDENCE_AGENT_INSTRUCTIONS,
        VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS,
        HPO_LINKING_AGENT_INSTRUCTIONS,
        MONDO_LINKING_AGENT_INSTRUCTIONS,
        COMPOUND_HET_AGENT_INSTRUCTIONS,
        SEGREGATION_ANALYSIS_COMPUTED_AGENT_INSTRUCTIONS,
    ],
)
def test_every_flagging_prompt_carries_the_rule_once_and_names_about(
    instructions,
):
    assert instructions.count('FLAGS -- decisions a curator should see') == 1
    assert '"about" is' in instructions
    # Each task names the kinds it may raise; the rest are not on offer.
    assert 'Kinds:' in instructions


def test_occurrence_prompt_links_a_parent_named_as_a_variants_origin():
    """A parental-inheritance statement is enough for a carrier link, flagged
    as inferred rather than left out: segregation reads parental genotypes
    from these links, and a run that excluded them (the COG4 paper, third
    local run) left segregation with nothing while another paper's run
    linked every parent -- the policy had to be stated."""
    prompt = PATIENT_VARIANT_OCCURRENCE_AGENT_INSTRUCTIONS
    assert "A parent named as the origin of a patient's variant carries it" in prompt
    assert 'Make the link in every case' in prompt
    assert 'the link is flagged as inferred\n  (below)' in prompt
    assert "Not\n  a parent named as a variant's origin" in prompt
    assert 'both parents of a homozygous child' in prompt
    # Two of three runs after the parent rule arrived dropped the child's own
    # link for the variant whose origin was named: the parent's link replaced
    # it rather than joining it. The check makes that an explicit miss.
    assert (
        "A parent's link is in addition to the child's, never instead of it" in prompt
    )
    assert 'A compound-heterozygous patient has one link per variant' in prompt
    # Naming a parent as the allele's origin supports "at least one copy", not
    # a genotype: zygosity is Unknown unless the paper gives the parent's own
    # result -- which it can do in the pedigree as well as in the text.
    assert 'then zygosity\n  is Unknown with that in its reasoning' in prompt
    assert "depends on whether the paper reports that parent's own genotype" in (prompt)


def test_occurrence_prompt_reads_a_pedigree_genotype_label_as_a_stated_genotype():
    """Paper 101 (CASP2): all nine parents came back with zygosity Unknown,
    with reasoning "own genotype not stated in the text", while the pedigree
    printed "+/-" under each genotyped parent with a chromatogram beside it
    and the text said "healthy family members had either heterozygous or
    wild-type alleles". The rule listed a table cell and a sentence as the
    ways a paper states a parent's genotype and put "a pedigree drawing the
    parent as a carrier" with the inferences; a genotype label is a result,
    a carrier symbol is a convention, and the prompt has to say which."""
    prompt = PATIENT_VARIANT_OCCURRENCE_AGENT_INSTRUCTIONS
    assert 'a genotype label printed against the person in the pedigree' in prompt
    assert "is the paper stating that person's result, exactly as a table cell" in (
        prompt
    )
    assert 'a half-filled or dotted\n    carrier symbol with no label' in prompt
    assert (
        'healthy family members\n    had either heterozygous or wild-type alleles'
        in (prompt)
    )
    assert 'stated rather than inferred, and the link is not flagged' in prompt
    assert 'a chromatogram shown for the person is such a report' in prompt
    # The flag kind no longer calls every pedigree-sourced zygosity inferred.
    assert 'Not a zygosity read from a genotype label in the pedigree' in prompt
    assert 'carries at least one copy and nothing more, so zygosity is Unknown' not in (
        prompt
    )


def test_occurrence_prompt_takes_a_whole_cohort_genotype_statement_as_stated():
    """The prompt already read a sentence about the tested relatives as a
    group as each relative's result, but scored anything else from "group
    context" moderate and flagged it inferred -- so a paper that gives every
    proband's zygosity in one sentence left every link Unknown. The same rule
    the demographics and phenotype prompts carry: a statement about every
    member of a group the paper puts the patient in is a statement about
    them; a share places nobody; a group whose members differ leaves the
    differing value to each patient's own result."""
    prompt = PATIENT_VARIANT_OCCURRENCE_AGENT_INSTRUCTIONS
    assert 'A statement about every member of the cohort or of a family' in prompt
    assert 'stated, cited to the sentence, high confidence, not\n  flagged' in prompt
    assert (
        'A share\n  of the group ("most", "15 of 18 probands") places nobody' in prompt
    )
    assert "leaves the zygosity\n  to each patient's own result" in prompt
    assert 'or a statement about every\n  member of a group' in prompt  # confidence
    assert 'or from a statement\n  about every member of the cohort or family' in prompt
    assert 'inferred from group/pedigree context' not in prompt


def test_patient_prompt_flag_examples_cover_the_three_kinds_of_decision():
    prompt = PATIENT_EXTRACTION_AGENT_INSTRUCTIONS
    assert 'FLAGS for this task' in prompt
    assert 'a rule here left out -- an earlier\n  study' in prompt
    assert 'a patient too, under that role; an empty record' in prompt
    assert '- inferred: a patient whose identifier is a positional label' in prompt
    assert 'a proband chosen where the paper marks none' in prompt
    # Proband and family membership are this task's to flag, nobody else's.
    assert 'a flag about them is raised\nhere or nowhere' in prompt
    assert 'has a flag\n  in "flags"; nothing routine does.' in prompt


def test_compound_het_prompt_flags_suggested_pairs_instead_of_grading_them():
    prompt = COMPOUND_HET_AGENT_INSTRUCTIONS
    assert 'confidence' not in prompt.lower()
    assert 'WHAT ONLY SUGGESTS A PAIR (output it, and flag it)' in prompt
    assert (
        'Not: a pair the paper establishes\noutright -- say nothing about it in "flags"'
        in prompt
    )


def test_demographics_prompt_reads_sex_from_the_pedigree_and_kinship_words():
    """Paper 101 (CASP2) came back with 10 of 22 patients' sex Unknown while the
    pedigree description gave a sex for every one of them; 86 patients across
    20 papers on dev carried the same reasoning. The field rule said "stated in
    text or pedigree" and guideline 1 listed "a sex from a pedigree symbol or a
    kinship word" among the values the paper merely implies -- so the same run
    read Male from one square and refused the next. A square or circle is the
    paper stating sex in pedigree notation, and "her brother" states it in
    words; neither is an inference."""
    prompt = PATIENT_DEMOGRAPHICS_AGENT_INSTRUCTIONS
    assert 'a square is the paper stating Male and a circle\n      Female' in prompt
    assert '"her brother" states Male for the brother' in prompt
    assert 'none of them\n    leaves sex Unknown' in prompt
    assert (
        'A pedigree symbol, a kinship word and a cohort or family\n   description are not implications'
        in prompt
    )
    assert 'a sex from a pedigree symbol or a kinship word' not in prompt
    # Text and figure disagreeing is a conflict to surface, not a coin flip.
    assert 'take the text\n    and raise a conflict flag' in prompt
    assert 'a "brother" drawn\n     as a circle' in prompt


def test_demographics_prompt_takes_ancestry_and_status_from_the_cohort_description():
    """Paper 109 (PKD1, "41 unrelated Thai families" in "an Asian population")
    came back with race Asian and country Thailand for most probands and
    Unknown for the rest, each run citing the no-inference guideline the
    other way; affected status was Unknown for a proband of the ADPKD cohort
    and Affected-by-genotype for another. Curators read a cohort description
    as the paper stating that fact for every member, so the prompt says so,
    says which groups count and which do not (a share, a mixed cohort), and
    keeps it off the flag list."""
    prompt = PATIENT_DEMOGRAPHICS_AGENT_INSTRUCTIONS
    assert 'COHORT AND FAMILY DESCRIPTIONS:' in prompt
    assert 'the paper stating\nthat fact for every member of the group' in prompt
    assert 'This is routine extraction, not a flag' in prompt
    # Each of the five fields points at the rule; sex lists what states it, so
    # the cohort sentence has to be on that list.
    for field in ('sex', 'country_of_origin', 'race', 'ethnicity', 'affected_status'):
        head = prompt.index(f'- {field} (')
        assert 'COHORT AND FAMILY DESCRIPTIONS' in prompt[head : head + 1300], field
    assert '"all affected\n      individuals were male"' in prompt
    # The enum is the census one, so a nationality maps to it deterministically.
    assert 'East, South and Southeast\n    Asia are Asian (Japanese, Chinese' in prompt
    assert (
        'An origin that is none\n    of those (a Finnish, Japanese or Nigerian population) states Not Hispanic'
        in prompt
    )
    # The limits: the patient's own statement wins, a share places nobody, a
    # mixed cohort fills only the field its parts agree on, an unaffected
    # relative is not a member of the disease cohort.
    assert 'A statement about the patient themself wins' in prompt
    assert (
        '("most were of European descent", "9 of 23 families were Finnish")' in prompt
    )
    assert 'Finnish and Estonian are both White' in prompt
    assert 'leaves the one that differs (country) Unknown' in prompt
    assert 'does not become Affected\n  because the cohort is' in prompt
    # The old openings that let a run refuse the cohort are gone, and genotype
    # alone still does not make a patient Affected.
    assert 'Extract from explicit geographic references\n' not in prompt
    assert 'Affected: explicitly reported condition' not in prompt
    assert 'a genotype alone is not\n    a report of the condition' in prompt
    assert 'a value taken from the cohort or family description' in prompt


def test_phenotype_prompt_takes_a_whole_cohort_finding_as_stated():
    """Paper 112 (ADAM22): "All affected individuals presented moderate-profound
    global developmental delay", scored 20/20 in the abstract, reached 7 of
    the 20 patients. The prompt said a cohort statement was evidence and then
    listed any finding taken from one as uncertain and flagged, so runs split
    between extracting it and leaving it. It is stated, for every member of a
    group the paper puts the patient in; a share ("12 of 20") places nobody."""
    prompt = PATIENT_PHENOTYPE_LINKING_AGENT_INSTRUCTIONS
    assert 'is the paper\nstating that finding for every member of the group' in prompt
    assert 'uncertain: false, cited to that\nsentence' in prompt
    assert (
        '"all affected\nindividuals" covers an Affected patient and not an Unaffected relative'
        in prompt
    )
    assert '"most", "the majority", 12 of 17 --\nnames nobody' in prompt
    # The column and the cohort sentence are two findings, not one, and the
    # dedup step keeps a pair the paper joins with a slash.
    assert 'the patient has both, and they are not duplicates' in prompt
    assert "are different by the paper's own account" in prompt
    assert 'the splitting rule below made them separate\nentries' in prompt
    # The flag kind keeps only the case where membership is unclear.
    assert 'a group the paper does not clearly place\n  them in' in prompt
    assert 'through a cohort-level or family-level sentence' not in prompt
    # The shared rule no longer calls every cohort sentence an inference.
    assert 'a family-level or cohort-level sentence' not in FLAG_RULES
    assert 'a group the paper does not place it in' in FLAG_RULES
