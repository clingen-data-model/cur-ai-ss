from agents import Agent

from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
from lib.agents.core_extraction_rules import FLAG_RULES
from lib.agents.model_factory import extraction_model, extraction_model_settings
from lib.models.patient_variant_occurrences import CompoundHetEvaluationOutput

COMPOUND_HET_AGENT_INSTRUCTIONS = """
Your task is to evaluate heterozygous variant pairs in a patient to determine if they represent
a compound heterozygous genotype (variants in trans on different chromosome copies).

CONTEXT:
- Patient identifier and paper context provided above
- The patient carries multiple heterozygous variants in the target gene
- Figures that could be read (a pedigree, parental Sanger traces, a gel) carry
  their description in the paper text, in a quoted "Figure description" block
  under their [figure-N] id: a trace or lane showing which parent carries which
  variant is evidence of phase, cited to that figure

INPUT:
A list of the patient's heterozygous variant links, including:
- variant_id
- variant descriptions (HGVS, rsID, etc.)

OUTPUT:
A JSON array of compound heterozygous pairs. Each pair includes:
- variant_id_a, variant_id_b (the two variant IDs)
- reasoning: the evidence that the two variants are in trans, citing the exact
  text, table, figure or pedigree it comes from

WHAT ESTABLISHES A PAIR:
- The text states that this patient is compound heterozygous for these variants, or
  names which variant sits on which allele or which parent each came from
- The pedigree shows each variant inherited from a different parent
- Parental testing confirms the variants are in trans
- Any of the above said about every compound heterozygous patient in the cohort
  ("parental testing confirmed the trans configuration in all cases", "each
  variant was inherited from a different parent in every family") is the paper
  saying it about this patient, when the paper puts them in that group; a
  statement about part of the group ("in most families") is not
- A table label ("c Het", "Comp Het") counts only together with one of the above for
  this patient, such as a statement that the parents of such patients carried one
  variant each

WHAT ONLY SUGGESTS A PAIR (output it, and flag it):
- A table zygosity label ("c Het", "Comp Het") or a family-level count of
  compound heterozygous families, with no parental genotypes and no statement of
  which allele or parent each variant is on for this patient. A label is the
  paper's conclusion, not the evidence of phase; say so in the flag.
- The segregation pattern implies trans without parental genotypes for both variants
  (e.g. one de novo variant plus one inherited variant in the same patient)
- Haplotype or linkage context indicates different chromosome copies
- The paper calls the patient compound heterozygous without saying which variants
- Two heterozygous variants co-occur with phase not established

RULES:
- Output a pair whenever the paper establishes it or suggests it; a pair the paper only
  suggests is flagged, since a curator can delete a pair but cannot easily build one
- A pair is never output twice, and a variant is in at most one pair
- Leave the pairs list empty only when the patient has more than two heterozygous variants
  and the paper gives no way to choose among them; flag that, naming the variants
- Each pair's reasoning should cite the exact evidence (quote from text, table/figure, pedigree)
"""

COMPOUND_HET_AGENT_INSTRUCTIONS = (
    COMPOUND_HET_AGENT_INSTRUCTIONS
    + '\n\n'
    + FLAG_RULES
    + """
FLAGS for this task. Kinds:
- inferred: a pair output on suggestive rather than established evidence --
  phase from segregation, from one parent's genotype alone, or from
  haplotype context. Say which.
- ambiguous: the paper calls the patient compound heterozygous naming no
  variants, or three or more heterozygous variants give no way to pair them.
- excluded: a heterozygous variant in the list that the paper never
  discusses for this patient.
Not: a pair the paper establishes
outright -- say nothing about it in "flags". "about" is a variant description from the list you were given, the two
of a pair written as "first / second", or null. The output carries a "flags"
list.
"""
)

agent = Agent(
    name='compound_het_evaluator',
    instructions=BASE_SYSTEM_INSTRUCTIONS,
    model=extraction_model(),
    model_settings=extraction_model_settings(),
    output_type=CompoundHetEvaluationOutput,
)
