"""The word "reasoning" never reaches a model (lib/agents/model_facing.py)."""

import json
import re

import pytest
from agents import Agent

from lib.agents import manual_output
from lib.agents.model_facing import (
    MODEL_FACING_WORD,
    STORED_WORD,
    ModelFacingOutputSchema,
    from_model_keys,
    model_facing_output,
    to_model_schema,
)
from lib.models.evidence_block import EvidenceBlock
from lib.models.patient import PatientExtractionOutput

_WORD = re.compile(STORED_WORD, re.IGNORECASE)


def test_schema_rename_covers_keys_required_defs_and_descriptions() -> None:
    schema = {
        '$defs': {
            'ReasoningBlock': {
                'properties': {
                    'value': {'type': 'string'},
                    'reasoning': {'type': 'string', 'description': 'your reasoning'},
                },
                'required': ['value', 'reasoning'],
                'title': 'ReasoningBlock',
            }
        },
        'properties': {'block': {'$ref': '#/$defs/ReasoningBlock'}},
    }
    out = to_model_schema(schema)
    block = out['$defs']['BasisBlock']
    assert set(block['properties']) == {'value', 'basis'}
    assert block['required'] == ['value', 'basis']
    assert block['properties']['basis']['description'] == 'your basis'
    assert out['properties']['block']['$ref'] == '#/$defs/BasisBlock'
    assert not _WORD.search(json.dumps(out))
    # the input is untouched
    assert 'ReasoningBlock' in schema['$defs']


def test_keys_map_back_at_any_depth_but_values_do_not() -> None:
    parsed = {
        'patients': [
            {
                'identifier': {
                    'value': 'basis of the study',
                    'basis': 'the paper names them',
                    'citations': [{'anchor': 'paragraph-1', 'quote': 'basis'}],
                }
            }
        ],
        'basis': 'top level too',
    }
    out = from_model_keys(parsed)
    block = out['patients'][0]['identifier']
    assert block['reasoning'] == 'the paper names them'
    assert 'basis' not in block
    assert block['value'] == 'basis of the study'
    assert block['citations'][0]['quote'] == 'basis'
    assert out['reasoning'] == 'top level too'


def test_wrapped_output_type_presents_basis_and_validates_reasoning() -> None:
    schema = model_facing_output(PatientExtractionOutput)
    assert isinstance(schema, ModelFacingOutputSchema)
    assert not schema.is_plain_text()
    assert schema.is_strict_json_schema()
    assert schema.name() == 'PatientExtractionOutput'
    text = json.dumps(schema.json_schema())
    assert not _WORD.search(text)
    assert f'"{MODEL_FACING_WORD}"' in text

    def block(value: object, basis: str) -> dict:
        return {
            'value': value,
            'basis': basis,
            'citations': [{'anchor': 'paragraph-3', 'quote': 'Patient 1'}],
        }

    reply = json.dumps(
        {
            'patients': [
                {
                    'identifier': block('Patient 1', 'named in the text'),
                    'family_identifier': block('Family A', 'the only family'),
                    'proband_status': block('Proband', 'the index case'),
                }
            ],
            'families': [
                {
                    'family': {
                        'identifier': block('Family A', 'the only family'),
                        'consanguinity': block(False, 'not stated'),
                    },
                    'patient_identifiers': [block('Patient 1', 'listed above')],
                }
            ],
            'flags': [],
        }
    )
    out = schema.validate_json(reply)
    assert isinstance(out, PatientExtractionOutput)
    assert out.patients[0].identifier.reasoning == 'named in the text'
    assert out.patients[0].proband_status.reasoning == 'the index case'
    assert out.families[0].patient_identifiers[0].reasoning == 'listed above'


def test_malformed_json_still_raises_the_sdk_error() -> None:
    from agents.exceptions import ModelBehaviorError

    with pytest.raises(ModelBehaviorError):
        model_facing_output(PatientExtractionOutput).validate_json('{not json')


def test_manual_output_directive_and_schema_use_the_model_facing_word() -> None:
    directive = manual_output.output_directive(EvidenceBlock[str])
    assert not _WORD.search(directive)
    assert MODEL_FACING_WORD in directive


def test_manual_output_parses_model_keys_back() -> None:
    text = json.dumps(
        {
            'value': 'x',
            'basis': 'why',
            'citations': [{'anchor': 'paragraph-0', 'quote': 'x'}],
        }
    )
    block = manual_output.parse_model_output(EvidenceBlock[str], text)
    assert block.reasoning == 'why'


def _all_agents() -> list[Agent]:
    from lib.agents import (
        compound_het_agent,
        extraction_verification_agent,
        hpo_linking_agent,
        mondo_linking_agent,
        paper_classifier_agent,
        paper_extraction_agent,
        patient_demographics_agent,
        patient_extraction_agent,
        patient_phenotype_linking_agent,
        patient_variant_occurrence_agent,
        segregation_analysis_computed_agent,
        segregation_evidence_extractor,
        variant_extraction_agent,
        variant_harmonization_agent,
    )

    return [
        m.agent
        for m in (
            compound_het_agent,
            extraction_verification_agent,
            hpo_linking_agent,
            mondo_linking_agent,
            paper_classifier_agent,
            paper_extraction_agent,
            patient_demographics_agent,
            patient_extraction_agent,
            patient_phenotype_linking_agent,
            patient_variant_occurrence_agent,
            segregation_analysis_computed_agent,
            segregation_evidence_extractor,
            variant_extraction_agent,
            variant_harmonization_agent,
        )
    ]


def test_every_structured_agent_output_schema_is_model_facing() -> None:
    for agent in _all_agents():
        if agent.output_type is None:
            continue
        assert isinstance(agent.output_type, ModelFacingOutputSchema), agent.name
        assert not _WORD.search(json.dumps(agent.output_type.json_schema())), agent.name


@pytest.mark.parametrize(
    'constant',
    [
        'lib.agents.core_extraction_rules.CORE_EXTRACTION_SPEC',
        'lib.agents.patient_extraction_agent.PATIENT_EXTRACTION_AGENT_INSTRUCTIONS',
        'lib.agents.patient_demographics_agent.PATIENT_DEMOGRAPHICS_AGENT_INSTRUCTIONS',
        'lib.agents.variant_extraction_agent.VARIANT_EXTRACTION_AGENT_INSTRUCTIONS',
        'lib.agents.patient_phenotype_linking_agent.PATIENT_PHENOTYPE_LINKING_AGENT_INSTRUCTIONS',
        'lib.agents.patient_variant_occurrence_agent.PATIENT_VARIANT_OCCURRENCE_AGENT_INSTRUCTIONS',
        'lib.agents.compound_het_agent.COMPOUND_HET_AGENT_INSTRUCTIONS',
        'lib.agents.paper_classifier_agent.PAPER_CLASSIFIER_AGENT_INSTRUCTIONS',
        'lib.agents.paper_extraction_agent.PAPER_EXTRACTION_AGENT_INSTRUCTIONS',
        'lib.agents.segregation_evidence_extractor.SEGREGATION_EVIDENCE_AGENT_INSTRUCTIONS',
        'lib.agents.segregation_analysis_computed_agent.SEGREGATION_ANALYSIS_COMPUTED_AGENT_INSTRUCTIONS',
        'lib.agents.hpo_linking_agent.HPO_LINKING_AGENT_INSTRUCTIONS',
        'lib.agents.mondo_linking_agent.MONDO_LINKING_AGENT_INSTRUCTIONS',
        'lib.agents.variant_harmonization_agent.VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS',
        'lib.agents.extraction_verification_agent.EXTRACTION_VERIFICATION_AGENT_INSTRUCTIONS',
    ],
)
def test_no_agent_prose_asks_for_reasoning(constant: str) -> None:
    """Every instructions constant that reaches a model says "basis"."""
    import importlib

    module_name, _, attr = constant.rpartition('.')
    text = getattr(importlib.import_module(module_name), attr)
    hits = sorted({m.group(0) for m in _WORD.finditer(text)})
    assert not hits, f'{constant} still says {hits}'
