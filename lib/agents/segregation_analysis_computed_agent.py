"""Agent for computing segregation analysis metrics per ClinGen SOP."""

import math
from collections import Counter

from agents import Agent, function_tool

from lib.core.environment import env
from lib.models.patient_variant_link import TestingMethod
from lib.models.segregation_analysis import (
    SegregationAnalysisComputedOutput,
    SequencingMethodology,
)

_DOMINANT_INHERITANCE_PATTERNS = {'Dominant', 'Semi-dominant', 'X-linked'}

_TESTING_TO_METHODOLOGY = {
    # Genome-wide / unbiased
    TestingMethod.chromosomal_microarray.value: SequencingMethodology.ExomeOrGenome.value,
    TestingMethod.exome_sequencing.value: SequencingMethodology.ExomeOrGenome.value,
    TestingMethod.genome_sequencing.value: SequencingMethodology.ExomeOrGenome.value,
    # Region defined first, then all genes
    TestingMethod.homozygosity_mapping.value: SequencingMethodology.AllGenesInRegion.value,
    TestingMethod.linkage_analysis.value: SequencingMethodology.AllGenesInRegion.value,
    # Targeted / candidate
    TestingMethod.next_generation_sequencing_panels.value: SequencingMethodology.CandidateGene.value,
    TestingMethod.sanger_sequencing.value: SequencingMethodology.CandidateGene.value,
    TestingMethod.pcr.value: SequencingMethodology.CandidateGene.value,
    TestingMethod.genotyping.value: SequencingMethodology.CandidateGene.value,
    TestingMethod.denaturing_gradient_gel.value: SequencingMethodology.CandidateGene.value,
    TestingMethod.high_resolution_melting.value: SequencingMethodology.CandidateGene.value,
    TestingMethod.restriction_digest.value: SequencingMethodology.CandidateGene.value,
    TestingMethod.single_strand_conformation_polymorphism.value: SequencingMethodology.CandidateGene.value,
    # Fallbacks
    TestingMethod.unknown.value: SequencingMethodology.Unknown.value,
    TestingMethod.other.value: SequencingMethodology.Unknown.value,
}


@function_tool
def compute_scoring_method(inheritance_values: list[str]) -> dict:
    """
    Derive the ClinGen scoring method from the most-frequent inheritance pattern
    across all patient-variant links in the family.
    Dominant / Semi-dominant / X-linked → 'Dominant'; all others → 'Recessive'.
    """
    if not inheritance_values:
        return {
            'scoring_method': None,
            'reasoning': 'No variant links found; cannot determine scoring method',
        }

    counts: Counter[str] = Counter(inheritance_values)
    most_common, count = counts.most_common(1)[0]
    method = (
        'Dominant' if most_common in _DOMINANT_INHERITANCE_PATTERNS else 'Recessive'
    )
    return {
        'scoring_method': method,
        'reasoning': (
            f'Most frequent inheritance: {most_common} ({count} of {len(inheritance_values)} links) → {method} scoring'
        ),
    }


@function_tool
def compute_sequencing_methodology(testing_method_values: list[str]) -> dict:
    """
    Derive the sequencing methodology from the most-frequent testing method
    across all patient-variant links in the family.
    """
    if not testing_method_values:
        return {
            'sequencing_methodology': SequencingMethodology.Unknown.value,
            'reasoning': 'No testing methods found; defaulting to Unknown',
        }

    counts: Counter[str] = Counter(testing_method_values)
    most_common, count = counts.most_common(1)[0]
    methodology = _TESTING_TO_METHODOLOGY.get(
        most_common, SequencingMethodology.Unknown.value
    )
    return {
        'sequencing_methodology': methodology,
        'reasoning': (
            f'Most frequent testing method: {most_common} ({count} of {len(testing_method_values)} methods) → {methodology}'
        ),
    }


@function_tool
def calculate_lod_score(
    segregation_count: int,
    affected_count: int,
    unaffected_count: int,
    scoring_method: str,
    extracted_lod_score: float | None,
) -> dict:
    """Calculate LOD score (tool for agent to call)."""
    if extracted_lod_score is not None:
        return {
            'lod_score': extracted_lod_score,
            'reasoning': f'Using published LOD score: {extracted_lod_score}',
        }

    if scoring_method == 'Dominant':
        denominator = (0.5) ** segregation_count
        lod_score = math.log10(1 / denominator) if denominator > 0 else 0.0
        return {
            'lod_score': round(lod_score, 2),
            'reasoning': f'Dominant: Z = log10(1/(0.5)^{segregation_count}) = {round(lod_score, 2)}',
        }

    elif scoring_method == 'Recessive':
        denominator = ((0.25) ** (affected_count - 1)) * ((0.75) ** unaffected_count)
        lod_score = math.log10(1 / denominator) if denominator > 0 else 0.0
        return {
            'lod_score': round(lod_score, 2),
            'reasoning': f'Recessive: Z = log10(1/((0.25)^{affected_count - 1} * (0.75)^{unaffected_count})) = {round(lod_score, 2)}',
        }

    return {'lod_score': 0.0, 'reasoning': f'Unknown scoring method: {scoring_method}'}


@function_tool
def check_minimum_criteria(
    segregation_count: int,
    affected_count: int,
    scoring_method: str,
    has_unexplainable_non_segregations: bool,
) -> dict:
    """Check if family meets ClinGen minimum criteria (tool for agent to call)."""
    failed = []

    if has_unexplainable_non_segregations:
        failed.append('Unexplainable non-segregations present')

    if scoring_method == 'Dominant':
        if segregation_count < 4:
            failed.append(
                f'Dominant requires 4+ segregations (has {segregation_count})'
            )
    elif scoring_method == 'Recessive':
        if affected_count < 3:
            failed.append(f'Recessive requires 3+ affected (has {affected_count})')
    else:
        raise ValueError(f'Received unexpected scoring method {scoring_method}')

    meets = len(failed) == 0
    return {
        'meets_criteria': meets,
        'reasoning': 'Meets all criteria' if meets else f'Fails: {"; ".join(failed)}',
    }


@function_tool
def assign_points(
    lod_score: float,
    sequencing_methodology: str,
    meets_minimum_criteria: bool,
) -> dict:
    """Assign points based on ClinGen matrix (tool for agent to call)."""
    if not meets_minimum_criteria:
        return {
            'points': 0.0,
            'reasoning': 'Family does not meet minimum criteria',
        }

    candidate_gene = {
        (0, 1.99): 0.0,
        (2, 2.99): 0.5,
        (3, 4.99): 1.0,
        (5, float('inf')): 1.5,
    }

    exome = {
        (0, 1.99): 0.0,
        (2, 2.99): 1.0,
        (3, 4.99): 2.0,
        (5, float('inf')): 3.0,
    }

    if sequencing_methodology in {
        SequencingMethodology.ExomeOrGenome.value,
        SequencingMethodology.AllGenesInRegion.value,
    }:
        matrix = exome
    elif sequencing_methodology == SequencingMethodology.CandidateGene.value:
        matrix = candidate_gene
    else:  # Unknown
        matrix = candidate_gene

    points = 0.0
    for (low, high), pts in matrix.items():
        if low <= lod_score <= high:
            points = pts
            break

    return {
        'points': points,
        'reasoning': f'LOD {lod_score} → {points} points using {sequencing_methodology}',
    }


SEGREGATION_ANALYSIS_COMPUTED_INSTRUCTIONS = """
System: You are an expert in ClinGen segregation analysis following the simplified LOD score methodology.

Task: Compute segregation analysis metrics for a family using ClinGen LOD score methodology.

You will receive:
1. Family structure (family identifier, patients with their affected/proband status)
2. Patient-variant links (which patients carry the variant, with zygosity, inheritance pattern, and testing methods)
3. Extracted segregation evidence (published LOD score if available, non-segregation flag)
4. Paper text for additional context

You have access to five tools:
- compute_scoring_method: Derives the ClinGen scoring method (Dominant/Recessive) from the inheritance values in the patient-variant links
- compute_sequencing_methodology: Derives the sequencing methodology from the testing methods in the patient-variant links
- check_minimum_criteria: Evaluates if family meets ClinGen size/segregation requirements
- calculate_lod_score: Computes LOD using ClinGen formulas (or uses published LOD if available)
- assign_points: Assigns points based on LOD score and sequencing methodology per Figure 6 matrix

Your task:

0. **Determine scoring method** (call compute_scoring_method tool first):
   - Collect all `inheritance` values from the patient-variant links
   - Pass them to `compute_scoring_method` to get the scoring method (Dominant or Recessive) and reasoning
   - Use this scoring method for all subsequent steps

0.5. **Determine sequencing methodology** (call compute_sequencing_methodology tool):
   - Flatten all `testing_methods` values from the patient-variant links into a single list
   - Pass them to `compute_sequencing_methodology` to get the sequencing methodology and reasoning
   - Use this methodology when calling `assign_points` in step 5

1. **Extract segregation count**: Count affected individuals (excluding proband) + obligate carriers, accounting for twins

   Base counting rule:
   - Start with number of affected individuals (phenotype+/genotype+)
   - Subtract 1 (the proband, whose genotype phase is unknown)
   - Add obligate carriers (even if untested or unaffected)

   Twin handling (CRITICAL):
   - **Dizygotic (fraternal) twins**: Each twin counts as a separate segregation
     * If proband has 2 dizygotic affected twin siblings with variant: +2 segregations
   - **Monozygotic (identical) twins**: Count as ONE segregation (not two)
     * If proband has 2 monozygotic affected twin siblings with variant: +1 segregation

   For dominant: count genotype+/phenotype+ individuals and obligate carriers
   For recessive: count differently (see ClinGen rules for sibling counting)

   Example: Proband + 2 dizygotic affected siblings with variant = 2 segregations (not 3)
   Example: Proband + 2 monozygotic affected siblings with variant = 1 segregation

   Provide detailed reasoning showing which individuals were counted and how twins were handled

2. **Extract affected/unaffected counts**:

   For **Dominant**:
   - affected_count: individuals with phenotype+
   - unaffected_count: not used in dominant formula, set to 0

   For **Recessive** (CRITICAL - parents excluded):
   - affected_count: number of affected siblings ONLY (not including parents)
   - unaffected_count: number of unaffected siblings ONLY (not including parents)
   - **DO NOT include parents in either count**, even if they are known carriers
   - Reasoning: Parents are obligate heterozygous carriers; only siblings are at same risk as proband to inherit two variants
   - Example: Proband (affected) + affected sibling + unaffected sibling + carrier parent = affected_count=1, unaffected_count=1 (parent excluded)

3. **Check minimum criteria** (call check_minimum_criteria tool):
   - Pass: segregation_count, affected_count, scoring_method, has_unexplainable_non_segregations
   - Returns: meets_criteria boolean and reasoning
   - Criteria: no unexplainable non-segregations, plus scoring-method-specific thresholds

4. **Calculate LOD score** (call calculate_lod_score tool):
   - Pass: segregation_count, affected_count, unaffected_count, scoring_method, extracted_lod_score
   - Returns: lod_score float and reasoning
   - Uses published LOD if available; otherwise applies ClinGen formula

5. **Assign points** (call assign_points tool):
   - Pass: lod_score, sequencing_methodology, meets_minimum_criteria boolean
   - Returns: points float and reasoning
   - Applies Figure 6 matrix based on methodology and criteria

Output all four computed values with clear reasoning.

## Edge Cases

- **Segregation count = 0**: Family has no segregations (only proband affected). LOD tools will handle gracefully.
- **Affected count = 0**: No affected individuals. LOD tools will detect criteria failure.
- **Unexplainable non-segregations**: Flag this immediately; family fails criteria.
- **Twins not specified**: Treat as unrelated individuals (conservative approach).
- **LOD score boundaries**: Tools handle boundaries correctly (e.g., exactly 2.0 goes to 2-2.99 row).
- **Unknown sequencing methodology**: Tools use conservative candidate gene matrix row.
"""

agent = Agent(
    name='segregation_analysis_computed',
    instructions=SEGREGATION_ANALYSIS_COMPUTED_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=SegregationAnalysisComputedOutput,
    tools=[
        compute_scoring_method,
        compute_sequencing_methodology,
        check_minimum_criteria,
        calculate_lod_score,
        assign_points,
    ],
)
