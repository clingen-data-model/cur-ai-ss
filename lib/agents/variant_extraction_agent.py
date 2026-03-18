from enum import Enum
from typing import List, Literal, Optional, Tuple

from agents import Agent, ModelSettings
from pydantic import BaseModel

from lib.core.environment import env

VARIANT_EXTRACTION_INSTRUCTIONS = """
System: You are an expert genomics curator.

Inputs:
- Target gene of interest
- Academic paper text

Task:
Extract all explicitly mentioned genetic variants associated with the target gene from the text.

------------------------------
Core Extraction Rules
------------------------------
1. Extract only variants explicitly stated in the provided text.
2. Include only variants clearly associated with the target gene.
3. If a variant lacks a gene name, include it only if the association is unambiguous.
4. Do NOT infer or normalize gene–variant associations.
5. Preserve all variant descriptions exactly as written.
6. Extract from all sections (main text, tables, figures, captions, supplements if included).
7. If a field is not provided or cannot be safely determined, return null.
8. Do NOT expand grouped variants unless individually specified.
9. Do NOT infer transcripts, coordinates, or accessions unless explicitly written.
10. Identifiers:
   - Extract rsIDs (e.g., rs123)
   - Extract CA IDs (e.g., CA123456)

------------------------------
Reference Sequences
------------------------------
Populate only if explicitly written:
- transcript → NM_, ENST
- protein_accession → NP_, ENSP
- genomic_accession → NC_, NG_
- lrg_accession → LRG_
- gene_accession → ENSG

Rules:
- Preserve exact formatting and version numbers
- Do NOT infer or convert between accession types
- If embedded in HGVS (e.g., NC_000007.13:g.123A>T), extract both:
  - Keep HGVS unchanged
  - Extract accession into appropriate field

------------------------------
Genomic Coordinates
------------------------------
Populate genomic_coordinates ONLY if explicitly stated.

Acceptable formats:
- chr7:140453136
- 7-140453136-A-T
- chr3:g.150928107A>C

Rules:
- Copy exactly as written
- Do NOT infer from HGVS or other fields
- Do NOT treat rsIDs or database IDs as coordinates

Genome build:
- Extract only if explicitly stated (e.g., GRCh37, hg19 → GRCh37)

------------------------------
HGVS Extraction (Explicit + Inferred)
------------------------------
Fields:
- hgvs_c
- hgvs_p
- hgvs_g

These fields may be populated in TWO ways:

1) Explicit HGVS:
   - If HGVS notation is directly written in the text, copy it exactly.

2) Inferred HGVS (Allowed with strict rules):
   You MAY infer HGVS only if:
   - The variant is described in a way that maps unambiguously to HGVS
     (e.g., "Val600Glu", "glycine to arginine at codon 12")
   - No transcript choice or coordinate resolution is required

   You MUST:
   - Use standard HGVS notation
   - NOT overwrite explicit HGVS if present
   - Leave null if ambiguity exists

For EACH HGVS field (c, p, g), you MUST provide:
- *_evidence_context → direct quote from text that supports the HGVS value
  - This may be:
    - the HGVS string itself (if explicit), OR
    - the descriptive variant text used for inference
- *_evidence_reasoning → explanation of how the value was obtained:
    - "explicitly stated in text" OR
    - clear reasoning for inference
    - Allowed inference examples:
        - "Val600Glu" → p.Val600Glu
        - "glycine to arginine at codon 12" → p.Gly12Arg
    - Disallowed inference:
        - exon-level descriptions without transcript
        - nucleotide changes without coordinate system
        - any case requiring transcript selection

If no HGVS value is assigned, all related fields must be null.
If reasoning cannot clearly justify the HGVS value, the HGVS field MUST be null.

------------------------------
Variant Type Classification
------------------------------
Use EXACT labels:
- missense
- frameshift
- stop gained
- splice donor
- splice acceptor
- splice region
- start lost
- inframe deletion
- frameshift deletion
- inframe insertion
- frameshift insertion
- structural
- synonymous
- intron
- 5' UTR
- 3' UTR
- non-coding
- unknown

Requirements:
- variant_type_evidence_context → direct quote if available
- variant_type_reasoning → explanation of classification

------------------------------
Evidence Rules (STRICT)
------------------------------
- ALL *_evidence_context fields MUST be:
  → direct verbatim quotes from the paper

- Evidence must:
  - directly support the field
  - NOT be paraphrased
  - NOT be inferred from other sections

- If no supporting quote exists:
  → set evidence_context = null
  → still provide reasoning if possible

------------------------------
Variant-Level Evidence
------------------------------
For each variant:
- variant_evidence_context → direct quote or text from table mentioning the variant
- variant_reasoning → explanation of how the variant was identified

------------------------------
Functional Evidence
------------------------------
Assess whether the paper provides experimental/functional validation.

functional_evidence:
- TRUE → if assays, experiments, or functional studies are described
- FALSE → otherwise

functional_evidence_evidence_context:
- Direct quote describing the functional experiment (or null)

functional_evidence_reasoning:
- REQUIRED explanation for the decision

------------------------------
Output Format
------------------------------
Return JSON:
{
  "variants": [...]
}

Rules:
- If no variants → return empty array []
- Use null for missing fields
- Do NOT include extra fields
- Do NOT use inferred fields to justify other inferred fields
- Each field must be independently supported by its own evidence and reasoning
"""


class VariantType(str, Enum):
    missense = 'missense'
    frameshift = 'frameshift'
    stop_gained = 'stop gained'
    splice_donor = 'splice donor'
    splice_acceptor = 'splice acceptor'
    splice_region = 'splice region'
    start_lost = 'start lost'
    inframe_deletion = 'inframe deletion'
    frameshift_deletion = 'frameshift deletion'
    inframe_insertion = 'inframe insertion'
    frameshift_insertion = 'frameshift insertion'
    structural = 'structural'
    synonymous = 'synonymous'
    intron = 'intron'
    five_utr = "5' UTR"
    three_utr = "3' UTR"
    non_coding = 'non-coding'
    unknown = 'unknown'


class HgvsInferenceConfidence(str, Enum):
    high = 'high'
    medium = 'medium'
    low = 'low'


class GenomeBuild(str, Enum):
    GRCh37 = 'GRCh37'
    GRCh38 = 'GRCh38'


class Variant(BaseModel):
    # Core extraction fields
    gene: str  # Not optional, statically comes from human

    # Reference sequences
    transcript: Optional[str]  # e.g., NM_or ENST
    protein_accession: Optional[str]  # e.g., NP_ or ENSP
    genomic_accession: Optional[str]  # e.g.  NC_ or NG_
    lrg_accession: Optional[str]  # e.g. LRG_
    gene_accession: Optional[str]  # e.g. ENSG

    genomic_coordinates: Optional[str]
    genome_build: Optional[GenomeBuild]
    rsid: Optional[str]
    caid: Optional[str]

    # Evidence
    variant_evidence_context: Optional[str]
    variant_reasoning: Optional[str]

    # Explicit HGVS from text
    hgvs_c: Optional[str]
    hgvs_c_evidence_context: Optional[str]
    hgvs_c_evidence_reasoning: Optional[str]
    hgvs_p: Optional[str]
    hgvs_p_evidence_context: Optional[str]
    hgvs_p_evidence_reasoning: Optional[str]
    hgvs_g: Optional[str]
    hgvs_g_evidence_context: Optional[str]
    hgvs_g_evidence_reasoning: Optional[str]

    # Variant Type
    variant_type: VariantType
    variant_type_evidence_context: Optional[str]
    variant_type_reasoning: Optional[str]

    # Functional evidence assessment
    functional_evidence: bool
    functional_evidence_evidence_context: Optional[str]
    functional_evidence_reasoning: str


class VariantExtractionOutput(BaseModel):
    variants: List[Variant]


agent = Agent(
    name='variant_extractor',
    instructions=VARIANT_EXTRACTION_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=VariantExtractionOutput,
)
