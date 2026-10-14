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
- Pedigree description (if available) showing family structure and inheritance

INPUT:
A list of the patient's heterozygous variant links, including:
- variant_id
- variant descriptions (HGVS, rsID, etc.)

OUTPUT:
A JSON array of compound heterozygous pairs. Each pair includes:
- variant_id_a, variant_id_b (the two variant IDs)
- confidence: a ReasoningBlock with:
  - value: confidence level ('confirmed', 'assumed', or 'uncertain')
  - reasoning: explanation of the evidence

CONFIDENCE LEVELS:

**Confirmed:**
- Paper explicitly states "compound heterozygous" or "compound het" for these variants
- Pedigree shows each variant inherited from a different parent (one from mother, one from father)
- Parental testing confirms variants are in trans (on different chromosomes)

**Assumed:**
- Segregation pattern strongly implies trans inheritance (e.g., de novo variant + inherited variant in same patient)
- Haplotype analysis or linkage disequilibrium context indicates variants are on different chromosomes
- Multiple affected family members share both variants in the same patient

**Uncertain:**
- Two variants co-occur in the same patient but phase is not established
- Indirect evidence suggesting compound heterozygosity without explicit confirmation
- Only a general statement that patient is "compound heterozygous" without variant mapping

RULES:
- A pair with explicit or strong inferential evidence of being in trans is "confirmed" or "assumed"
- When the paper calls the patient compound heterozygous without saying which variants, or
  two heterozygous variants co-occur with phase unknown, output the pair with confidence
  "uncertain" and flag it -- a curator can delete a pair but cannot easily build one
- Leave the pairs list empty only when the patient has more than two heterozygous variants
  and the paper gives no way to choose among them; flag that, naming the variants
- Each pair's reasoning should cite the exact evidence (quote from text, table/figure, pedigree)
"""

COMPOUND_HET_AGENT_INSTRUCTIONS = (
    COMPOUND_HET_AGENT_INSTRUCTIONS
    + '\n\n'
    + FLAG_RULES
    + """
FLAGS for this task: a pair output as "uncertain" because the paper did not
say which variants or did not establish phase, a phase inferred from one
parent's genotype alone, three or more heterozygous variants with no way to
pair them, a heterozygous variant in the list that the paper never discusses
for this patient. "about" is a variant description from the list you were given, or
null. The output carries a "flags" list.
"""
)

agent = Agent(
    name='compound_het_evaluator',
    instructions=BASE_SYSTEM_INSTRUCTIONS,
    model=extraction_model(),
    model_settings=extraction_model_settings(),
    output_type=CompoundHetEvaluationOutput,
)
