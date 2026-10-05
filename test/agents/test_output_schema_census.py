"""Every agent's output schema fits Anthropic's structured-output limit.

Anthropic's tool-schema compiler dereferences every ``$ref`` and caps the
result at 16 union/nullable nodes (``docs/anthropic-migration.md``, Blocker 4).
Pydantic renders a nullable field as ``anyOf: [{type}, {type: null}]`` and a
union the same way, so the count is the number of ``anyOf`` nodes in the
dereferenced schema (a schema with a list-valued ``type`` would count too; the
SDK's strict mode never emits one). An evidence block embeds ``Citation``,
which is all-``str`` inside a plain list, so a block adds only its value's own
nullability, however many times it appears.

Slice 4 of ``docs/evidence-anchors-plan.md`` removed the legacy
``quote``/``table_id``/``image_id`` nullables from ``EvidenceBlock``, which
brought the four over-limit agents (variant extraction 61, patient extraction
18, demographics 40, occurrences 20) under it. The exact counts are pinned so a
model change that moves them is a conscious edit here, not a 400 from the
provider on the next live run.

The union count is necessary, not sufficient: variant extraction (13) and
demographics (7) still fail with "The compiled grammar is too large", an
undocumented limit on the dereferenced schema's overall size (live on
2026-09-30; a Variant with 8 evidence fields compiles, 12 does not). Those two
run with ``output_type=None`` through ``run_with_manual_output``; the set is
pinned here so switching one back is a conscious edit too.
"""

import copy
from typing import Any

import pytest
from agents import AgentOutputSchema

from lib.agents.compound_het_agent import agent as compound_het_agent
from lib.agents.hpo_linking_agent import agent as hpo_linking_agent
from lib.agents.mondo_linking_agent import agent as mondo_linking_agent
from lib.agents.paper_classifier_agent import agent as paper_classifier_agent
from lib.agents.paper_extraction_agent import agent as paper_extraction_agent
from lib.agents.patient_demographics_agent import agent as patient_demographics_agent
from lib.agents.patient_extraction_agent import agent as patient_extraction_agent
from lib.agents.patient_phenotype_linking_agent import (
    agent as patient_phenotype_linking_agent,
)
from lib.agents.patient_variant_occurrence_agent import (
    agent as patient_variant_occurrence_agent,
)
from lib.agents.pedigree_describer_agent import PedigreeExtractionOutput
from lib.agents.segregation_analysis_computed_agent import (
    agent as segregation_analysis_computed_agent,
)
from lib.agents.segregation_evidence_extractor import (
    agent as segregation_evidence_agent,
)
from lib.agents.table_correction_agent import TableCorrectionResult
from lib.agents.variant_extraction_agent import agent as variant_extraction_agent
from lib.agents.variant_harmonization_agent import agent as variant_harmonization_agent
from lib.models.patient import PatientDemographics
from lib.models.variant import VariantExtractionOutput

ANTHROPIC_UNION_NODE_LIMIT = 16

# Module-level agents, plus the output types of the two agents that are built
# per call (pedigree describer, table corrector) because they close over a
# paper id for their tools.
OUTPUT_TYPES: dict[str, Any] = {
    agent.name: agent.output_type
    for agent in (
        compound_het_agent,
        hpo_linking_agent,
        mondo_linking_agent,
        paper_extraction_agent,
        paper_classifier_agent,
        patient_demographics_agent,
        patient_extraction_agent,
        patient_phenotype_linking_agent,
        patient_variant_occurrence_agent,
        segregation_analysis_computed_agent,
        segregation_evidence_agent,
        variant_extraction_agent,
        variant_harmonization_agent,
    )
} | {
    'pedigree_describer': PedigreeExtractionOutput,
    'table_corrector': TableCorrectionResult,
}

# The four agents slice 4 took under the union limit, with their counts.
UNDER_THE_UNION_LIMIT_SINCE_SLICE_4 = {
    'variant_extractor': 13,
    'patient_info_extractor': 0,
    'patient_demographics_extractor': 7,
    'patient_variant_occurrence': 2,
}

# The two whose dereferenced schema is still too large for the grammar
# compiler; their output_type is None and the schema travels in the prompt.
MANUAL_OUTPUT = {'variant_extractor', 'patient_demographics_extractor'}

MODELS_BEHIND_MANUAL_OUTPUT: dict[str, Any] = {
    'variant_extractor': VariantExtractionOutput,
    'patient_demographics_extractor': PatientDemographics,
}


def _dereference(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if '$ref' in node:
            name = node['$ref'].rsplit('/', 1)[1]
            return _dereference(copy.deepcopy(defs[name]), defs)
        return {key: _dereference(value, defs) for key, value in node.items()}
    if isinstance(node, list):
        return [_dereference(value, defs) for value in node]
    return node


def _count_union_nodes(node: Any) -> int:
    if isinstance(node, dict):
        own = int('anyOf' in node or isinstance(node.get('type'), list))
        return own + sum(_count_union_nodes(value) for value in node.values())
    if isinstance(node, list):
        return sum(_count_union_nodes(value) for value in node)
    return 0


def union_node_count(output_type: Any) -> int:
    """Union/nullable nodes in the schema the SDK sends for ``output_type``."""
    schema = copy.deepcopy(AgentOutputSchema(output_type).json_schema())
    defs = schema.pop('$defs', {})
    return _count_union_nodes(_dereference(schema, defs))


def _schema_for(name: str) -> Any:
    return MODELS_BEHIND_MANUAL_OUTPUT.get(name) or OUTPUT_TYPES[name]


def test_exactly_the_grammar_limited_agents_run_without_a_native_schema():
    manual = {name for name, output_type in OUTPUT_TYPES.items() if output_type is None}
    assert manual == MANUAL_OUTPUT


@pytest.mark.parametrize('name', sorted(OUTPUT_TYPES))
def test_output_schema_fits_the_anthropic_union_limit(name):
    assert union_node_count(_schema_for(name)) <= ANTHROPIC_UNION_NODE_LIMIT


@pytest.mark.parametrize(
    'name, expected', sorted(UNDER_THE_UNION_LIMIT_SINCE_SLICE_4.items())
)
def test_slice_4_agents_keep_their_union_counts(name, expected):
    assert union_node_count(_schema_for(name)) == expected
