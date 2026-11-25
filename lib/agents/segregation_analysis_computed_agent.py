"""Agent for computing segregation analysis metrics per ClinGen SOP."""

import math
from collections import Counter

from agents import Agent, function_tool

from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
from lib.agents.core_extraction_rules import FLAG_RULES
from lib.agents.model_facing import model_facing_output
from lib.agents.model_factory import decision_model_settings, extraction_model
from lib.models.patient_variant_occurrences import TestingMethod
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
    TestingMethod.mlpa.value: SequencingMethodology.CandidateGene.value,
    TestingMethod.single_strand_conformation_polymorphism.value: SequencingMethodology.CandidateGene.value,
    # Fallbacks
    TestingMethod.unknown.value: SequencingMethodology.Unknown.value,
    TestingMethod.other.value: SequencingMethodology.Unknown.value,
}


def scoring_method(inheritance_values: list[str]) -> dict:
    """The ClinGen scoring method from the most frequent inheritance value
    across the family's links: Dominant / Semi-dominant / X-linked score as
    Dominant, Recessive as Recessive, and anything else -- Unknown,
    Mitochondrial, Somatic Mosaicism -- gives no method, so the family is not
    scored. Until 2026-11-23 anything not dominant scored as Recessive, so a
    family whose links mostly said Unknown silently got the recessive formula,
    counting rules and minimum.
    """
    if not inheritance_values:
        return {
            'scoring_method': None,
            'reasoning': 'No variant links found; cannot determine scoring method',
        }

    counts: Counter[str] = Counter(inheritance_values)
    most_common, count = counts.most_common(1)[0]
    if most_common in _DOMINANT_INHERITANCE_PATTERNS:
        method: str | None = 'Dominant'
    elif most_common == 'Recessive':
        method = 'Recessive'
    else:
        method = None
    tally = f'Most frequent inheritance: {most_common} ({count} of {len(inheritance_values)} links)'
    if method is None:
        return {
            'scoring_method': None,
            'reasoning': f'{tally}, which has no ClinGen segregation formula; the family is not scored',
        }
    return {'scoring_method': method, 'reasoning': f'{tally} → {method} scoring'}


@function_tool
def compute_scoring_method(inheritance_values: list[str]) -> dict:
    """Derive the ClinGen scoring method (Dominant or Recessive) from the
    family's inheritance values; null when the most frequent value is
    Unknown or not Mendelian, and then the family is not scored."""
    return scoring_method(inheritance_values)


# Broadest first: the SOP awards more points when the linkage interval was
# searched more completely.
_METHODOLOGY_BREADTH = [
    SequencingMethodology.ExomeOrGenome.value,
    SequencingMethodology.AllGenesInRegion.value,
    SequencingMethodology.CandidateGene.value,
    SequencingMethodology.Unknown.value,
]


def sequencing_methodology(
    testing_methods: list[str], source: str = 'the proband'
) -> dict:
    """The family's sequencing methodology: the broadest one among the
    proband's own testing methods (or, when no proband has a link, every
    tested member's -- the handler decides, and ``source`` names which).

    SOP v12, p. 35: "typically only the proband needs to have undergone
    [exome/genome] sequencing to be counted in this segregation method,
    whereas family members may have undergone exome/genome or Sanger
    sequencing alone." This used to be the most frequent method across every
    link in the family, so relatives confirmed by Sanger -- or, since the
    occurrence prompt began giving a tested relative with no named method
    Unknown (2026-11-23), relatives tested by an unnamed method -- could
    outvote a proband's exome and move the family to the candidate-gene
    points row.
    """
    methodologies = {
        _TESTING_TO_METHODOLOGY.get(m, SequencingMethodology.Unknown.value)
        for m in testing_methods
    }
    if not methodologies:
        return {
            'sequencing_methodology': SequencingMethodology.Unknown.value,
            'reasoning': f'No testing method from {source}; defaulting to Unknown',
        }
    broadest = next(m for m in _METHODOLOGY_BREADTH if m in methodologies)
    return {
        'sequencing_methodology': broadest,
        'reasoning': (
            f'Testing methods from {source} ({", ".join(sorted(set(testing_methods)))}) '
            f'make the broadest methodology {broadest}'
        ),
    }


@function_tool
def compute_sequencing_methodology(testing_methods: list[str], source: str) -> dict:
    """Derive the family's sequencing methodology, the broadest of the given
    testing methods. Pass sequencing_methods.testing_methods and
    sequencing_methods.source from the family data, unchanged."""
    return sequencing_methodology(testing_methods, source)


def lod_score(
    segregation_count: int,
    affected_count: int,
    unaffected_count: int,
    scoring_method: str | None,
    extracted_lod_score: float | None,
) -> dict:
    """The family's LOD score per the ClinGen Gene-Disease Validity SOP (v12,
    pp. 29-32): a published LOD as given, else the simplified estimate.

    Recessive: Z = log10(1 / (0.25^(affected - 1) * 0.75^unaffected)), where
    ``affected_count`` includes the proband -- the SOP's "# of Affected
    Individuals - 1" is the segregations from the proband. It used to be
    passed affected siblings only and subtracted one again, so a proband with
    one affected brother scored 0.0 instead of 0.6 (dev, paper 146, 2026-11-23).
    """
    if extracted_lod_score is not None:
        return {
            'lod_score': extracted_lod_score,
            'reasoning': f'Using published LOD score: {extracted_lod_score}',
        }

    if scoring_method == 'Dominant':
        lod = segregation_count * math.log10(2)
        return {
            'lod_score': round(lod, 2),
            'reasoning': f'Dominant: Z = log10(1/(0.5)^{segregation_count}) = {round(lod, 2)}',
        }

    if scoring_method == 'Recessive':
        affected_segregations = max(affected_count - 1, 0)
        lod = affected_segregations * math.log10(4) + unaffected_count * math.log10(
            4 / 3
        )
        return {
            'lod_score': round(lod, 2),
            'reasoning': (
                f'Recessive: Z = log10(1/((0.25)^({affected_count}-1) * '
                f'(0.75)^{unaffected_count})) = {round(lod, 2)}, counting '
                f'{affected_count} affected including the proband'
            ),
        }

    return {'lod_score': 0.0, 'reasoning': f'Unknown scoring method: {scoring_method}'}


@function_tool
def calculate_lod_score(
    segregation_count: int,
    affected_count: int,
    unaffected_count: int,
    scoring_method: str | None,
    extracted_lod_score: float | None,
) -> dict:
    """Calculate the family's LOD score. affected_count includes the proband;
    a published LOD score, when given, is used as is."""
    return lod_score(
        segregation_count,
        affected_count,
        unaffected_count,
        scoring_method,
        extracted_lod_score,
    )


def minimum_criteria(
    segregation_count: int,
    affected_count: int,
    scoring_method: str | None,
    has_unexplainable_non_segregations: bool,
    extracted_lod_score: float | None,
) -> dict:
    """Whether the family's LOD may be scored (SOP v12, p. 29).

    The size minimums -- 4 segregations dominant, 3 affected including the
    proband recessive -- are conditions for *estimating* a LOD. A published
    LOD is used as the authors give it, so a family with one is not held to
    them; it used to be, and scored 0 points whenever fewer segregations were
    counted than the minimum. An unexplainable non-segregation fails a family
    either way.
    """
    failed = []

    if has_unexplainable_non_segregations:
        failed.append('Unexplainable non-segregations present')

    if extracted_lod_score is None:
        if scoring_method == 'Dominant':
            if segregation_count < 4:
                failed.append(
                    f'Dominant requires 4+ segregations (has {segregation_count})'
                )
        elif scoring_method == 'Recessive':
            if affected_count < 3:
                failed.append(
                    'Recessive requires 3+ affected including the proband '
                    f'(has {affected_count})'
                )
        else:
            failed.append(f'No scoring method ({scoring_method})')

    meets = len(failed) == 0
    if meets and extracted_lod_score is not None:
        reasoning = 'Published LOD score: the family-size minimums do not apply'
    else:
        reasoning = 'Meets all criteria' if meets else f'Fails: {"; ".join(failed)}'
    return {'meets_criteria': meets, 'reasoning': reasoning}


@function_tool
def check_minimum_criteria(
    segregation_count: int,
    affected_count: int,
    scoring_method: str | None,
    has_unexplainable_non_segregations: bool,
    extracted_lod_score: float | None,
) -> dict:
    """Check whether the family meets the ClinGen criteria for scoring.
    affected_count includes the proband; pass the published LOD score, or
    null when the paper gives none."""
    return minimum_criteria(
        segregation_count,
        affected_count,
        scoring_method,
        has_unexplainable_non_segregations,
        extracted_lod_score,
    )


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

INPUT (database-derived, no paper text):
1. Family structure (family identifier, patients with their affected/proband status, relationships,
   and each patient's genotype for each segregating variant -- see GENOTYPES), plus
   segregating_variant_ids and sequencing_methods (the testing methods that set the
   methodology, and their source)
2. Patient-variant links (which patients carry the variant, with zygosity, inheritance pattern, and testing methods)
3. Extracted segregation evidence (published LOD score if available, and has_unexplainable_non_segregations, a true/false value)

Flags raised by other steps are never part of the input; who was tested comes only from the genotype field.

You have access to five tools:
- compute_scoring_method: Derives the ClinGen scoring method (Dominant/Recessive) from the inheritance values in the patient-variant links
- compute_sequencing_methodology: Derives the sequencing methodology from the testing methods in sequencing_methods
- check_minimum_criteria: Evaluates if family meets ClinGen size/segregation requirements
- calculate_lod_score: Computes LOD using ClinGen formulas (or uses published LOD if available); its affected_count includes the proband
- assign_points: Assigns points based on LOD score and sequencing methodology per Figure 6 matrix

Your task:

0. **Determine scoring method** (call compute_scoring_method tool first):
   - Collect all `inheritance` values from the patient-variant links
   - Pass them to `compute_scoring_method` to get the scoring method (Dominant or Recessive) and basis
   - Use this scoring method for all subsequent steps
   - When it returns null (the family's inheritance is mostly Unknown, or not
     Mendelian), the family is not scored: count nothing (all counts 0), still
     call the remaining tools with scoring_method null -- the minimum criteria
     then fail and points are 0, unless a published LOD stands on its own --
     and raise an unresolved flag naming the inheritance values

0.5. **Determine sequencing methodology** (call compute_sequencing_methodology tool):
   - Pass `sequencing_methods.testing_methods` and `sequencing_methods.source`
     unchanged. They are the proband's testing methods: the SOP grades the
     family by how the proband's variant was found, not by how relatives were
     confirmed. When no proband has a variant link, the source says so and the
     methods are every tested member's: raise an inferred flag saying the
     methodology was not taken from a proband
   - Use this methodology when calling `assign_points` in step 5

GENOTYPES

The ClinGen SOP counts only people whose genotype is known: an affected
person counts when they were tested and carry the variant, never because
they are affected. Segregation is about the segregating variants
(segregating_variant_ids): the proband's, or, when no proband has a link,
every variant linked in the family. Each patient's "genotype" maps each
segregating variant id to what their link to it shows:
- "tested carrier": the link carries a testing method -- the paper reports
  this person's own result for that variant.
- "untested carrier": the link has no testing method -- the variant is
  placed on them by inference (a carrier symbol with no genotype label, a
  parent named as the variant's origin, a parent of a homozygous child).
- "no result": no link to that variant. Not tested, or tested negative: the
  two cannot be told apart here, so "no result" is never counted as
  genotyped, in either direction.
Read the genotype variant by variant: a person tested for one variant and
inferred for another is a tested carrier of the first only. A link to any
variant not in segregating_variant_ids never counts. The proband is the
index case and is counted as a tested carrier of their own variants whatever
their links show.

1. **Count segregations (Dominant / X-linked)**:
   - Count every affected person other than the proband who is a "tested
     carrier" of a segregating variant.
   - Add each obligate carrier: a person who must carry the variant because
     of where they sit in the pedigree -- between two carriers in a line of
     descent (a parent with the variant and a child with the variant; a
     sibling with the variant and a child with the variant). An obligate
     carrier counts whatever their phenotype and whether or not they were
     tested. Name in the basis the carriers on either side of them.
   - An "untested carrier" who is not an obligate carrier by that test is
     not counted, and neither is any affected person with "no result": an
     affected relative counts only once tested.
   - A tested carrier who is unaffected is not counted (reduced penetrance or
     later onset can explain them) unless they are an obligate carrier.
   - Twins: dizygotic twins count as two segregations, monozygotic as one.
     Twins of unstated type are counted as two, flagged inferred.
   Example: affected proband, affected tested-carrier sister, affected
   untested aunt, untested mother whose own mother is an affected tested
   carrier = 3 segregations (sister, mother as obligate carrier, grandmother);
   the aunt is not counted.

   **Recessive**: segregation_count is affected_count - 1.

   Name in the basis every person counted and every affected person left
   out, with the reason.

2. **Count affected and unaffected**:

   For **Dominant / X-linked**:
   - affected_count: the proband plus the affected people counted in step 1
   - unaffected_count: 0 (not used)

   For **Recessive** -- only the proband and their siblings, the people at
   the same risk of inheriting both copies; parents and other relatives are
   never counted:
   - affected_count: the proband plus each affected sibling with the
     proband's genotype, tested: a "tested carrier" of the proband's variant
     with a homozygous link, or of both of a compound-heterozygous proband's
     variants. The proband is included.
   - unaffected_count: each unaffected sibling who was tested and found not
     to share the proband's genotype -- a tested carrier of one variant only.
     A sibling with "no result" is not counted: tested-negative siblings
     cannot be told from untested ones here, and leaving them out errs low.
   - When the proband is compound heterozygous and no parent is a tested
     carrier, the variants are not shown to be in trans: count no siblings
     (affected_count 1, unaffected_count 0) and flag inferred.
   Example: affected proband (homozygous), affected tested-homozygous
   sister, unaffected tested-heterozygous brother, untested unaffected sister,
   carrier parents = affected_count 2, unaffected_count 1.

3. **Check minimum criteria** (call check_minimum_criteria tool):
   - Pass: segregation_count, affected_count, scoring_method,
     has_unexplainable_non_segregations, extracted_lod_score
   - Criteria: no unexplainable non-segregations; and, for an estimated LOD
     only, at least 4 segregations (Dominant) or at least 3 affected
     including the proband (Recessive). A published LOD is not held to the
     size minimums.

4. **Calculate LOD score** (call calculate_lod_score tool):
   - Pass: segregation_count, affected_count, unaffected_count, scoring_method, extracted_lod_score
   - Returns: lod_score float and basis
   - Uses published LOD if available; otherwise applies ClinGen formula

5. **Assign points** (call assign_points tool):
   - Pass: lod_score, sequencing_methodology, meets_minimum_criteria boolean
   - Returns: points float and basis
   - Applies Figure 6 matrix based on methodology and criteria

Output all six computed values with clear basis: segregation_count, affected_count, unaffected_count, computed_lod_score, points_assigned, meets_minimum_criteria.

Basis is read by human curators — write it in plain language. Do not use raw tool or function names (e.g. compute_scoring_method, assign_points); describe what was computed and why instead (e.g., "Inheritance values indicate dominant pattern, so dominant LOD formula applied").

## Edge Cases

- **Segregation count = 0**: Family has no segregations (only proband affected). LOD tools will handle gracefully.
- **Affected count = 0**: No affected individuals. LOD tools will detect criteria failure.
- **Unexplainable non-segregations**: Flag this immediately; family fails criteria.
- **Twins not specified**: Treat as unrelated individuals (conservative approach).
- **LOD score boundaries**: Tools handle boundaries correctly (e.g., exactly 2.0 goes to 2-2.99 row).
- **Unknown sequencing methodology**: Tools use conservative candidate gene matrix row.
"""

SEGREGATION_ANALYSIS_COMPUTED_AGENT_INSTRUCTIONS = (
    SEGREGATION_ANALYSIS_COMPUTED_INSTRUCTIONS
    + '\n\n'
    + FLAG_RULES
    + """
FLAGS for this task. Kinds:
- inferred: a family member counted or left out on an assumption -- an
  unknown affected status, an obligate carrier counted untested, twins of
  unstated type, siblings left out because the variants are not phased, a
  methodology or segregating variants taken without a linked proband.
- conflict: a count the extracted LOD score disagrees with.
- unresolved: no scoring method, because the family's inheritance is mostly
  Unknown or not Mendelian, so the family is not scored.
Not: a methodology defaulted to the conservative row (the rule decides it),
a non-segregation treated as explained (the evidence extractor raises that), nor
the genotypes and statuses you were given. "about" is a member's identifier
from the family structure, or null. The output carries a "flags" list.
"""
)

agent = Agent(
    name='segregation_analysis_computed',
    instructions=BASE_SYSTEM_INSTRUCTIONS,
    model=extraction_model(),
    model_settings=decision_model_settings(),
    output_type=model_facing_output(SegregationAnalysisComputedOutput),
    tools=[
        compute_scoring_method,
        compute_sequencing_methodology,
        check_minimum_criteria,
        calculate_lod_score,
        assign_points,
    ],
)
