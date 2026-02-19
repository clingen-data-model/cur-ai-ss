from enum import Enum
from typing import List, Literal, Optional, Tuple

from agents import Agent, ModelSettings
from pydantic import BaseModel

from lib.evagg.utils.environment import env

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
8. Variants are considered distinct if their verbatim descriptions differ except when the source explicitly reports multiple descriptions
(e.g., cDNA and protein) for the same molecular change. In such cases, combine them into a single variant object and populate all explicitly provided HGVS fields without creating duplicates.
9. Do not expand grouped variants (e.g. "Three different missense variants were found in this family") unless each is individually listed.
10. Do not resolve or infer transcripts, genomic coordinates, or gene names.
11. If there is an explicitly stated rsID (e.g. rs527413419) or ClinGen Allele Registry ID (e.g. CA321211) provide 
them in the rsid and caid fields respectively.

Reference Sequence Handling:
- If an NM_ or ENST accession is explicitly written, populate transcript_accession.
- If an NP_ or ENSP accession is explicitly written, populate protein_accession.
- If an NC_ or NG_ accession is explicitly written, populate genomic_accession.
- If an LRG accession (LRG_*) is written, preserve exactly as written and populate lrg_accession.
- If an ENSG accession is written, preserve exactly as written and populate gene_accession.

- If multiple reference accessions are explicitly written (e.g., transcript and protein),
  populate each appropriate field independently.
- Do NOT validate biological consistency between them.

- Preserve all accessions exactly as written, including version numbers.
- If no version is present, do NOT infer or append one.
- Do NOT normalize accession formatting.

- If a reference sequence is embedded inside an HGVS string 
  (e.g., NC_000007.13:g.140453136A>T),
  extract the accession into the appropriate reference field AND preserve the full HGVS string unchanged.
- Strict Non-Inference Rules:
  - Do NOT derive NP_ from NM_.
  - Do NOT derive NM_ from NP_.
  - Do NOT derive NC_ from genomic coordinates.
  - Do NOT convert LRG to NM_ or ENST.
  - Do NOT infer genome build from coordinates alone.
  - Do NOT populate a reference sequence field if HGVS is written without an explicit accession.
  - Do NOT modify HGVS strings to match extracted reference fields.


Examples of variant_description_verbatim:
- "Val600Glu mutation"
- "c.1799T>A in exon 15"
- "glycine to arginine substitution at codon 12"

Genomic Coordinates Handling:
- Populate genomic_coordinates **only if the paper explicitly provides a genomic location** of the variant.
- Acceptable formats include:
    - Chromosome and position: "chr7:140453136", "7:140453136"
    - Chromosome, position, and alleles: "chr7:140453136 A>T", "7-140453136-A-T", "chr3:g.150928107A>C"
    - gnomAD-style coordinate strings: e.g., "gnomAD: 7-140453136-A-T", "chr7-140453136-A-T"
- Copy coordinates **exactly as written**, without modification or normalization.
- Do NOT infer coordinates from HGVS, transcripts, amino acid changes, exon numbers, or other descriptions.
- Do NOT treat identifiers alone as coordinates:
    - Examples to ignore: rsIDs ("rs113488022"), gnomAD allele IDs ("gnomAD allele ID 123456"), ClinVar IDs
- If only an identifier is provided, or no genomic location is explicitly stated, return null.
- If the genome assembly (e.g., GRCh37, GRCh38, hg19, hg38) is explicitly stated in the text, 
extract it into a separate field (genome_build).  You may infer hg19 -> GRCh37 and hg38 -> GRCh38.

HGVS Genomic Handling:
- Populate hgvs_g only if a genomic HGVS expression (e.g., NC_000007.13:g.140453136A>T) is explicitly written in the source text.
- Do not infer hgvs_g from cDNA, protein, transcript, exon number, or chromosomal coordinates.
- Accept g. notation even if reference sequence prefix is absent, but only if explicitly written as g.

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
6. If the source explicitly reports both a cDNA change and the resulting protein change for the same variant, populate both hgvs_c and hgvs_p in a single variant object. 
Use the text surrounding the variant to determine that they refer to the same molecular change. Evidence context should include both mentions.

Examples of allowed inference:
- “glycine to arginine substitution at codon 12” → p.Gly12Arg
- “Val600Glu mutation” → p.Val600Glu

Examples of disallowed inference:
- exon-level deletions without transcript context
- cDNA numbering without a reference transcript
- variants requiring coordinate resolution

For each extracted variant, provide:
- gene
- transcript (e.g. NM_ )
- protein accession (e.g. NP_ )
- genomic accession (e.g NC_ )
- variant_description_verbatim (exact text describing the variant from source)
- genomic_coordinates
- genome_build
- rsid
- hgvs_g
- hgvs_c
- hgvs_p
- hgvs_c_inferred
- hgvs_p_inferred
- hgvs_c_inference_confidence (one of "high", "medium", "low", or null)
- hgvs_c_inference_evidence_context
- hgvs_p_inference_confidence (one of "high", "medium", "low", or null)
- hgvs_p_inference_evidence_context
- variant_type (must match above labels exactly)

Evidence Handling:
- Each variant must have its own supporting evidence context.
- variant_evidence_context: Exact text from source stating the variant.
- variant_type_evidence_context: Exact text explicitly stating the variant type, if applicable.
- hgvs_c_inference_evidence_context: Exact text used to justify any inferred hgvs.c, if applicable.
- hgvs_p_inference_evidence_context: Exact text used to justify any inferred hgvs.p, if applicable.
- Copy all evidence text verbatim.
- Evidence must be directly linked to each claim and not from different sections.
- If no explicit evidence is available for a field, return null.

Output:
- Return a JSON object with a single field: variants (array of variant objects as above).
- If none found for the target gene, return an empty array: [].
- For any undetermined field, use null.
- Do not include extra fields.
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

    variant_description_verbatim: Optional[str]
    genomic_coordinates: Optional[str]
    genome_build: Optional[GenomeBuild]
    rsid: Optional[str]
    caid: Optional[str]

    # Explicit HGVS from text
    hgvs_c: Optional[str]
    hgvs_p: Optional[str]
    hgvs_g: Optional[str]

    # Optional inferred HGVS (clearly labeled)
    hgvs_c_inferred: Optional[str]
    hgvs_p_inferred: Optional[str]
    hgvs_p_inference_confidence: Optional[HgvsInferenceConfidence]
    hgvs_p_inference_evidence_context: Optional[str]
    hgvs_c_inference_confidence: Optional[HgvsInferenceConfidence]
    hgvs_c_inference_evidence_context: Optional[str]

    variant_type: VariantType

    # Evidence
    variant_evidence_context: Optional[str]
    variant_type_evidence_context: Optional[str]


class VariantExtractionOutput(BaseModel):
    variants: List[Variant]


agent = Agent(
    name='variant_extractor',
    instructions=VARIANT_EXTRACTION_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=VariantExtractionOutput,
)
