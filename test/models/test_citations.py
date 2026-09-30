"""The ``citations`` field on EvidenceBlock: grammar check, source rule, schema
budget, storage compatibility and the ``prune_citations`` safety net.
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
    EvidenceBlock,
    HumanEvidenceBlock,
    prune_citations,
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


# --- prune_citations ---------------------------------------------------------

TEXTS = {
    'paragraph-1': 'The proband carried c.1220C>A and was  diagnosed at 5.',
    'table-1': 'Table 1. Variants\n| Patient | Variant |\n| P1 | c.1220C>A<sup>a</sup> |',
    'table-1-row-0': '| P1 | c.1220C>A<sup>a</sup> |',
    'figure-2': 'Figure 2. Pedigree',
}


def test_prune_drops_unknown_anchors(caplog):
    block = _block(
        citations=[
            Citation(anchor='paragraph-1'),
            Citation(anchor='paragraph-999'),
            Citation(anchor='table-1-row-9'),
        ]
    )

    with caplog.at_level(logging.WARNING, logger='lib.models.evidence_block'):
        changed = prune_citations(block, TEXTS)

    assert changed == 2
    assert [c.anchor for c in block.citations] == ['paragraph-1']
    assert sum('unknown anchor' in r.getMessage() for r in caplog.records) == 2


def test_prune_blanks_quotes_the_block_does_not_contain(caplog):
    block = _block(citations=[Citation(anchor='paragraph-1', quote='c.1220C>T')])

    with caplog.at_level(logging.WARNING, logger='lib.models.evidence_block'):
        changed = prune_citations(block, TEXTS)

    assert changed == 1
    assert block.citations == [Citation(anchor='paragraph-1', quote='')]
    assert any('Blanking quote' in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(
    'anchor, quote',
    [
        ('paragraph-1', 'c.1220C>A'),
        ('paragraph-1', 'was diagnosed at 5'),  # doubled space in the block
        ('table-1-row-0', 'c.1220C>A'),  # footnote marker in the cell
        ('table-1-row-0', '| P1 | c.1220C>A |'),  # a copied row
        ('table-1', 'Table 1. Variants'),  # the caption, at table level
        ('table-1', 'P1 | c.1220C>A'),  # a row, at table level
    ],
)
def test_prune_keeps_tolerant_matches(anchor, quote):
    block = _block(citations=[Citation(anchor=anchor, quote=quote)])

    assert prune_citations(block, TEXTS) == 0
    assert block.citations[0].quote == quote


def test_prune_does_not_fold_case():
    block = _block(citations=[Citation(anchor='paragraph-1', quote='THE PROBAND')])

    assert prune_citations(block, TEXTS) == 1
    assert block.citations[0].quote == ''


def test_prune_leaves_legacy_fields_and_empty_quotes_alone():
    block = _block(
        quote='not in any block',
        table_id=3,
        citations=[Citation(anchor='figure-2')],
    )

    assert prune_citations(block, TEXTS) == 0
    assert block.quote == 'not in any block'
    assert block.table_id == 3
    assert block.citations == [Citation(anchor='figure-2', quote='')]


def test_prune_walks_nested_output_in_place():
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
    links = output.links

    assert prune_citations(output, TEXTS) == 5
    assert output.links is links  # pruned in place, nothing rebuilt
    for link in output.links:
        assert link.zygosity.citations[0].quote == 'c.1220C>A'
        assert link.inheritance.citations == []
        assert link.testing_methods[0].citations[0].quote == ''
    assert output.disease_name is not None
    assert output.disease_name.citations == []


def test_prune_accepts_bare_lists_and_dicts():
    blocks = [_block(citations=[Citation(anchor='paragraph-1')]) for _ in range(2)]

    assert prune_citations(blocks, TEXTS) == 0
    assert prune_citations({'a': _block(citations=[Citation(anchor='table-7')])}, TEXTS)
    assert prune_citations('not a model', TEXTS) == 0
