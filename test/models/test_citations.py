"""The ``citations`` field on EvidenceBlock: grammar check, source rule, schema
budget, storage compatibility and the ``verify_citations`` check.
``test_evidence_markup.py`` stays about markup stripping."""

import logging

import pytest
from agents.strict_schema import ensure_strict_json_schema
from litellm.llms.anthropic.chat.transformation import AnthropicConfig

from lib.bin.strip_evidence_markup import _clean
from lib.models import PaperExtractionOutput
from lib.models.base import manual_evidence_block
from lib.models.evidence_block import (
    AttributedEvidenceBlock,
    Citation,
    CitationError,
    EvidenceBlock,
    HumanEvidenceBlock,
    verify_citations,
)
from lib.models.patient_variant_occurrences import (
    Inheritance,
    PatientVariantOccurrence,
    PatientVariantOccurrenceOutput,
    TestingMethod,
    Zygosity,
)


def _block(**kwargs) -> EvidenceBlock[str]:
    return EvidenceBlock[str](value='x', reasoning='r', **kwargs)


# --- Citation ---------------------------------------------------------------


def test_citation_defaults_and_stripping():
    citation = Citation(anchor='  paragraph-3 ', quote='c.1220C>A<sup>a</sup>')

    assert citation.anchor == 'paragraph-3'
    assert citation.quote == 'c.1220C>A'
    assert Citation(anchor='figure-0').quote == ''


# --- the grammar check on EvidenceBlock ---------------------------------------


@pytest.mark.parametrize(
    'anchor',
    ['paragraph-12', 'table-1', 'table-1-row-7', 'figure-0', 'supp-table-1-row-7'],
)
def test_well_formed_anchor_survives(anchor):
    block = _block(citations=[Citation(anchor=anchor)])

    assert [c.anchor for c in block.citations] == [anchor]


@pytest.mark.parametrize('anchor', ['paragraph-3-row-1', 'Table 1', 'p54', ''])
def test_malformed_anchor_is_dropped_with_a_warning(anchor, caplog):
    with caplog.at_level(logging.WARNING, logger='lib.models.evidence_block'):
        block = _block(quote='x', citations=[Citation(anchor=anchor)])

    assert block.citations == []
    warnings = [r for r in caplog.records if 'malformed anchor' in r.getMessage()]
    assert len(warnings) == 1
    assert repr(anchor) in warnings[0].getMessage()


def test_citation_alone_satisfies_the_source_rule():
    block = _block(citations=[Citation(anchor='paragraph-1')])

    assert block.quote is None
    assert block.table_id is None


def test_only_a_malformed_citation_is_no_source():
    with pytest.raises(ValueError, match='evidence source'):
        _block(citations=[Citation(anchor='p1')])


def test_response_blocks_need_no_source_and_do_not_share_the_default():
    attributed = AttributedEvidenceBlock[str](value='x', reasoning='r')
    human = HumanEvidenceBlock[str](value='x', reasoning='r')

    assert attributed.citations == [] and human.citations == []
    attributed.citations.append(Citation(anchor='table-0'))
    assert human.citations == []
    assert HumanEvidenceBlock[str](value='x', reasoning='r').citations == []


# --- storage compatibility --------------------------------------------------


def test_legacy_stored_block_loads_with_no_citations():
    stored = {'value': 'x', 'reasoning': 'r', 'quote': 'q', 'is_supplement': False}

    block = HumanEvidenceBlock[str].model_validate(stored)

    assert block.citations == []


def test_dumps_carry_citations():
    block = _block(citations=[Citation(anchor='table-1-row-2', quote='c.1A>G')])

    assert block.model_dump()['citations'] == [
        {'anchor': 'table-1-row-2', 'quote': 'c.1A>G'}
    ]
    assert manual_evidence_block('x')['citations'] == []


# --- schema budget: nothing here may add a union node ----------------------


def _walk(node, found):
    if isinstance(node, dict):
        if 'anyOf' in node or 'oneOf' in node:
            found.append(node)
        for value in node.values():
            _walk(value, found)
    elif isinstance(node, list):
        for item in node:
            _walk(item, found)


def test_citation_schema_has_no_union_nodes():
    schema = EvidenceBlock[str].model_json_schema()

    found: list = []
    _walk(schema['$defs']['Citation'], found)
    _walk(schema['properties']['citations'], found)
    assert found == []
    assert schema['properties']['citations']['default'] == []


def test_strict_schema_accepts_citations_as_required():
    strict = ensure_strict_json_schema(PaperExtractionOutput.model_json_schema())

    block = next(v for k, v in strict['$defs'].items() if k.startswith('EvidenceBlock'))
    assert 'citations' in block['required']
    assert strict['$defs']['Citation']['required'] == ['anchor', 'quote']


def test_anthropic_output_schema_filter_keeps_the_empty_default():
    filtered = AnthropicConfig.filter_anthropic_output_schema(
        EvidenceBlock[str].model_json_schema()
    )

    assert filtered['properties']['citations']['default'] == []


# --- the stored-markup cleaner sees the nested quote --------------------------


def test_strip_script_cleans_citation_quotes():
    stored = {
        'value': 'x',
        'reasoning': 'r',
        'citations': [{'anchor': 'table-1-row-2', 'quote': 'Fs 3<sup>g</sup>'}],
    }

    assert _clean(stored) == 1
    assert stored['citations'][0]['quote'] == 'Fs 3'


# --- verify_citations --------------------------------------------------------

TEXTS = {
    'paragraph-1': 'The proband carried c.1220C>A and was  diagnosed at 5.',
    'table-1': 'Table 1. Variants\n| Patient | Variant |\n| P1 | c.1220C>A<sup>a</sup> |',
    'table-1-row-0': '| P1 | c.1220C>A<sup>a</sup> |',
    'figure-2': 'Figure 2. Pedigree',
}


def test_unknown_anchors_are_an_error_naming_each_one():
    block = _block(
        citations=[
            Citation(anchor='paragraph-1'),
            Citation(anchor='paragraph-999'),
            Citation(anchor='table-1-row-9'),
        ]
    )

    with pytest.raises(CitationError) as exc:
        verify_citations(block, TEXTS)

    message = str(exc.value)
    assert message.startswith('2 citation(s) do not check out')
    assert "citations[1]: anchor 'paragraph-999' does not exist" in message
    assert "citations[2]: anchor 'table-1-row-9' does not exist" in message
    assert 'paragraph-1' not in message.split('\n', 1)[1]  # the good one is not listed


def test_a_quote_the_block_does_not_contain_is_an_error():
    block = _block(citations=[Citation(anchor='paragraph-1', quote='c.1220C>T')])

    with pytest.raises(
        CitationError, match="quote 'c.1220C>T' is not found verbatim in paragraph-1"
    ):
        verify_citations(block, TEXTS)


def test_nothing_is_mutated_on_failure():
    """The model, not the code, corrects a bad citation: the block is untouched."""
    citations = [
        Citation(anchor='paragraph-1', quote='nope'),
        Citation(anchor='table-7'),
    ]
    block = _block(citations=list(citations))

    with pytest.raises(CitationError):
        verify_citations(block, TEXTS)

    assert block.citations == citations


@pytest.mark.parametrize(
    'anchor, quote',
    [
        ('paragraph-1', 'c.1220C>A'),
        ('paragraph-1', 'was diagnosed at 5'),  # doubled space in the block
        ('table-1-row-0', 'c.1220C>A'),  # footnote marker in the cell
        ('table-1-row-0', '| P1 | c.1220C>A |'),  # a copied row
        ('table-1', 'Table 1. Variants'),  # the caption, at table level
        ('table-1', 'P1 | c.1220C>A'),  # a row, at table level
        ('figure-2', ''),  # a figure is cited without a quote
    ],
)
def test_tolerant_matches_pass(anchor, quote):
    verify_citations(_block(citations=[Citation(anchor=anchor, quote=quote)]), TEXTS)


def test_case_is_not_folded():
    block = _block(citations=[Citation(anchor='paragraph-1', quote='THE PROBAND')])

    with pytest.raises(CitationError):
        verify_citations(block, TEXTS)


def test_legacy_fields_are_not_checked():
    block = _block(
        quote='not in any block',
        table_id=3,
        citations=[Citation(anchor='figure-2')],
    )

    verify_citations(block, TEXTS)


def test_nested_output_is_walked_and_every_problem_has_a_path():
    def occurrence() -> PatientVariantOccurrence:
        return PatientVariantOccurrence(
            patient_id=1,
            variant_id=2,
            zygosity=EvidenceBlock(
                value=Zygosity.heterozygous,
                reasoning='r',
                citations=[Citation(anchor='table-1-row-0', quote='c.1220C>A')],
            ),
            inheritance=EvidenceBlock(
                value=Inheritance.dominant,
                reasoning='r',
                citations=[Citation(anchor='paragraph-77')],
            ),
            de_novo=EvidenceBlock(value=False, reasoning='r'),
            testing_methods=[
                EvidenceBlock(
                    value=TestingMethod.exome_sequencing,
                    reasoning='r',
                    citations=[Citation(anchor='paragraph-1', quote='nope')],
                )
            ],
        )

    output = PatientVariantOccurrenceOutput(
        links=[occurrence(), occurrence()],
        disease_name=EvidenceBlock(
            value='X', reasoning='r', citations=[Citation(anchor='figure-9')]
        ),
    )

    with pytest.raises(CitationError) as exc:
        verify_citations(output, TEXTS)

    lines = str(exc.value).splitlines()
    assert lines[0].startswith('5 citation(s)')
    assert "- links[0].inheritance.citations[0]: anchor 'paragraph-77'" in lines[1]
    assert "- links[0].testing_methods[0].citations[0]: quote 'nope'" in lines[2]
    assert lines[3].startswith('- links[1].inheritance')
    assert lines[5].startswith("- disease_name.citations[0]: anchor 'figure-9'")


def test_bare_lists_and_dicts_and_non_models():
    verify_citations([_block(citations=[Citation(anchor='paragraph-1')])] * 2, TEXTS)
    verify_citations('not a model', TEXTS)
    with pytest.raises(CitationError, match=r"\['a'\]\.citations\[0\]"):
        verify_citations({'a': _block(citations=[Citation(anchor='table-7')])}, TEXTS)
