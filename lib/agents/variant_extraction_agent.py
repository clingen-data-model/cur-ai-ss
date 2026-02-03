VARIANT_EXTRACTION_INSTRUCTIONS = """
System: You are an expert genomics curator.

Inputs:
- Target gene of interest
- Academic paper text

Task: Extract all explicitly mentioned genetic variants associated with the target gene from the text.

Extraction Guidelines:
1. Extract only variants explicitly stated in the provided text.
2. Include only variants clearly associated with the target gene.
3. If a variant lacks a gene name, include it only if the association to the target gene is unambiguous in the text.
4. Do not infer or normalize gene–variant associations beyond what is written, except where explicitly allowed under HGVS Inference (Optional).
5. Preserve the original variant wording exactly as in the source.
6. Extract variants from main text, tables, figure captions, and explicitly referenced supplements.
7. If a field is not provided, return null for that field.
8. Do not merge distinct variants.
9. Do not expand grouped variants unless each is individually listed.
10. Do not resolve or infer transcripts, genomic coordinates, or gene names.

Transcript Handling:
- Extract transcript identifiers only if explicitly stated (e.g., NM_002448.3, ENST00000312345).
- Do not add, infer, or substitute transcript identifiers.
- Preserve transcript identifiers exactly as written.
- If absent, return null.

Examples of variant_verbatim:
- "Val600Glu mutation"
- "c.1799T>A in exon 15"
- "glycine to arginine substitution at codon 12"

Genomic Coordinates Handling:
- Populate genomic_coordinates **only if the paper explicitly provides a genomic location** of the variant.
- Acceptable formats include:
    - Chromosome and position: "chr7:140453136", "7:140453136"
    - Chromosome, position, and alleles: "chr7:140453136 A>T", "7-140453136-A-T"
    - gnomAD-style coordinate strings: e.g., "gnomAD: 7-140453136-A-T", "chr7-140453136-A-T"
- Copy coordinates **exactly as written**, without modification or normalization.
- Do NOT infer coordinates from HGVS, transcripts, amino acid changes, exon numbers, or other descriptions.
- Do NOT treat identifiers alone as coordinates:
    - Examples to ignore: rsIDs ("rs113488022"), gnomAD allele IDs ("gnomAD allele ID 123456"), ClinVar IDs
- If only an identifier is provided, or no genomic location is explicitly stated, return null.

Variant Type Classification (use these labels exactly):
- "missense": single amino acid change
- "frameshift": insertion or deletion causing a frameshift
- "stop gained": nonsense mutation introducing a stop codon
- "splice donor": affects the canonical donor splice site
- "splice acceptor": affects the canonical acceptor splice site
- "splice region": affects nearby nucleotides outside the canonical site
- "start lost": affects the start codon
- "inframe deletion": deletion of codons without frameshift
- "frameshift deletion": deletion causing frameshift
- "inframe insertion": insertion of codons without frameshift
- "frameshift insertion": insertion causing frameshift
- "structural": large-scale structural variants (duplication, inversion, CNV, translocation)
- "synonymous": no amino acid change
- "intron": variant in an intron
- "5' UTR": in 5' untranslated region
- "3' UTR": in 3' untranslated region
- "non-coding": other non-coding variant
- "unknown": type cannot be determined

HGVS Inference (Optional, Controlled):
You may optionally infer HGVS notation (hgvs_c_inferred, hgvs_p_inferred) only under the following conditions:
1. Infer HGVS only if the variant is described in human-readable form (e.g., amino acid substitution or codon-level description) and the mapping to HGVS is unambiguous.
2. Do not infer HGVS if doing so would require:
   - choosing between multiple transcripts
   - assuming a reference sequence not explicitly stated
   - resolving exon numbering to genomic or cDNA coordinates
3. Do not modify or normalize the original variant wording.
4. Never overwrite hgvs_c or hgvs_p if they are explicitly provided in the source text.
5. If no safe inference can be made, all inferred fields must be null.

Examples of allowed inference:
- “glycine to arginine substitution at codon 12” → p.Gly12Arg
- “Val600Glu mutation” →v p.Val600Glu

Examples of disallowed inference:
- exon-level deletions without transcript context
- cDNA numbering without a reference transcript
- variants requiring coordinate resolution

For each extracted variant, provide:
- gene
- transcript
- variant_verbatim (exact text describing the variant from source)
- genomic_coordinates
- hgvs_c
- hgvs_p
- hgvs_c_inferred
- hgvs_p_inferred
- hgvs_inference_confidence (one of "high", "medium", "low", or null)
- hgvs_inference_evidence_context
- variant_type (must match above labels exactly)
- zygosity (one of "homozygous", "hemizygous", "heterozygous", "compound heterozygous", "unknown")
- inheritance (one of "dominant", "recessive", "semi-dominant", "X-linked", "de novo", "somatic mosaicism", "mitochondrial", or "unknown")

Evidence Handling:
- Each variant must have its own supporting evidence context.
- variant_evidence_context: Exact text from source stating the variant.
- variant_type_evidence_context: Exact text explicitly stating the variant type, if applicable.
- zygosity_evidence_context: Exact text explicitly stating zygosity, if available.
- inheritance_evidence_context: Exact text explicitly stating inheritance, if available.
- hgvs_inference_evidence_context: Exact text used to justify any inferred HGVS, if applicable.
- Copy all evidence text verbatim.
- Evidence must be directly linked to each claim and not from different sections.
- If no explicit evidence is available for a field, return null.

Output:
- Return a JSON object with a single field: variants (array of variant objects as above).
- If none found for the target gene, return an empty array: [].
- For any undetermined field, use null.
- Do not include extra fields.
"""

from enum import Enum
from typing import List, Literal, Optional, Tuple

from agents import Agent, ModelSettings
from pydantic import BaseModel

from lib.evagg.utils.environment import env


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


class Zygosity(str, Enum):
    homozygous = 'homozygous'
    hemizygous = 'hemizygous'
    heterozygous = 'heterozygous'
    compound_heterozygous = 'compound heterozygous'
    unknown = 'unknown'


class Inheritance(str, Enum):
    dominant = 'dominant'
    recessive = 'recessive'
    semi_dominant = 'semi-dominant'
    x_linked = 'X-linked'
    de_novo = 'de novo'
    somatic_mosaicism = 'somatic mosaicism'
    mitochondrial = 'mitochondrial'
    unknown = 'unknown'


class HgvsInferenceConfidence(str, Enum):
    high = 'high'
    medium = 'medium'
    low = 'low'


class Variant(BaseModel):
    # Core extraction fields
    gene: str  # Not optional, statically comes from human
    transcript: Optional[str]
    variant_verbatim: Optional[str]
    genomic_coordinates: Optional[str]

    # Explicit HGVS from text
    hgvs_c: Optional[str]
    hgvs_p: Optional[str]

    # Optional inferred HGVS (clearly labeled)
    hgvs_c_inferred: Optional[str]
    hgvs_p_inferred: Optional[str]
    hgvs_inference_confidence: Optional[HgvsInferenceConfidence]
    hgvs_inference_evidence_context: Optional[str]

    # Other variant attributes
    variant_type: VariantType
    zygosity: Zygosity
    inheritance: Inheritance

    # Evidence
    variant_type_evidence_context: Optional[str]
    variant_evidence_context: Optional[str]
    zygosity_evidence_context: Optional[str]
    inheritance_evidence_context: Optional[str]


class VariantExtractionOutput(BaseModel):
    variants: List[Variant]


agent = Agent(
    name='variant_extractor',
    instructions=VARIANT_EXTRACTION_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=VariantExtractionOutput,
)
