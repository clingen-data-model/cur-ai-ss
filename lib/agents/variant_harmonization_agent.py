from enum import Enum
from typing import List, Literal, Optional, Tuple
from urllib.parse import quote

import requests
from agents import Agent, function_tool
from pydantic import BaseModel

from lib.agents.variant_extraction_agent import GenomeBuild, VariantExtractionOutput
from lib.evagg.utils.environment import env

CLINGEN_ALLELE_REGISTRY_ENDPOINT = 'https://reg.genome.network'
VV_GENE2TRANSCRIPTSV1_ENDPOINT = (
    'https://rest.variantvalidator.org/VariantValidator/tools/gene2transcripts'
)
VV_GENE2TRANSCRIPTSV2_ENDPOINT = (
    'https://rest.variantvalidator.org/VariantValidator/tools/gene2transcripts_v2'
)
VV_VARIANT_VALIDATOR_ENDPOINT = (
    'https://rest.variantvalidator.org/VariantValidator/variantvalidator'
)
VV_VARIANT_VALIDATOR_ENSEMBL_ENDPOINT = (
    'https://rest.variantvalidator.org/VariantValidator/variantvalidator_ensembl'
)


@function_tool
def allele_registry_resolver(
    gnomad_style_coordinates: str | None,
    rsid: str | None,
    caid: str | None,
) -> Optional[dict[str, str | None]]:
    if caid:
        suffix = f'allele/{quote(caid)}'
    elif gnomad_style_coordinates:
        suffix = f'alleles?gnomAD_4.id={quote(gnomad_style_coordinates)}'
    elif rsid:
        suffix = f'alleles?dbSNP.rs={quote(rsid)}'
    else:
        return None

    url = f'{CLINGEN_ALLELE_REGISTRY_ENDPOINT}/{suffix}'
    headers = {'content-type': 'application/json'}

    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()

    data = r.json()
    if not data:
        return None

    # If query endpoint returned a list, take first match
    if isinstance(data, list):
        data = data[0]

    # --- CAID ---
    resolved_caid = None
    allele_id_url = data.get('@id')
    if allele_id_url:
        resolved_caid = allele_id_url.rstrip('/').split('/')[-1]

    # --- gnomAD v4 ---
    resolved_gnomad = None
    gnomad_v4_records = data.get('externalRecords', {}).get('gnomAD_4', [])
    if gnomad_v4_records:
        resolved_gnomad = gnomad_v4_records[0].get('id')

    # --- rsID ---
    resolved_rsid = None
    dbsnp_records = data.get('externalRecords', {}).get('dbSNP', [])
    if dbsnp_records:
        rs_value = dbsnp_records[0].get('rs')
        if rs_value is not None:
            resolved_rsid = f'rs{rs_value}'

    # -----------------------
    # Genomic HGVS (prefer GRCh38)
    # -----------------------
    resolved_hgvsg = None

    for g in data.get('genomicAlleles', []):
        genome = g.get('referenceGenome')
        hgvs_list = g.get('hgvs', [])
        if not hgvs_list:
            continue

        if genome == 'GRCh38':
            resolved_hgvsg = hgvs_list[0]
            break

    # fallback if no GRCh38 found
    if not resolved_hgvsg:
        for g in data.get('genomicAlleles', []):
            hgvs_list = g.get('hgvs', [])
            if hgvs_list:
                resolved_hgvsg = hgvs_list[0]
                break

    # -----------------------
    # Transcript HGVS (prefer MANE Select RefSeq)
    # -----------------------
    resolved_hgvsc = None
    resolved_hgvsp = None
    found_mane = False

    for t in data.get('transcriptAlleles', []):
        mane = t.get('MANE')
        if mane and mane.get('maneStatus') == 'MANE Select':
            # Prefer MANE Select RefSeq
            refseq_nuc = mane.get('nucleotide', {}).get('RefSeq', {}).get('hgvs')
            refseq_pro = mane.get('protein', {}).get('RefSeq', {}).get('hgvs')

            if refseq_nuc:
                resolved_hgvsc = refseq_nuc
            if refseq_pro:
                resolved_hgvsp = refseq_pro

            found_mane = True
            continue  # still finish loop, but ignore fallbacks

        # Fallback collection (only if MANE not found yet)
        if not found_mane:
            if not resolved_hgvsc:
                for h in t.get('hgvs', []):
                    if ':c.' in h:
                        resolved_hgvsc = h
                        break

            if not resolved_hgvsp:
                protein_hgvs = t.get('proteinEffect', {}).get('hgvs')
                if protein_hgvs:
                    resolved_hgvsp = protein_hgvs

    return {
        'gnomad_style_coordinates': resolved_gnomad,
        'rsid': resolved_rsid,
        'caid': resolved_caid,
        'hgvs_c': resolved_hgvsc,
        'hgvs_g': resolved_hgvsg,
        'hgvs_p': resolved_hgvsp,
    }


@function_tool
def gnomad_style_id_from_variant_validator(variant_description: str) -> str | None:
    """
    Given an arbitrary variant_description (hgvsg, hgvsc, hgvsp), use VariantValidator
    to return a GRCh38 mapped gnomad-style variant id.

    Internally supports both RefSeq and Ensembl

    Example Output: 1-55051215-G-GA

    """
    encoded_variant_description = quote(variant_description, safe='')
    endpoint = (
        VV_VARIANT_VALIDATOR_ENSEMBL_ENDPOINT
        if variant_description.strip().startswith(('ENST', 'ENSP', 'ENSG'))
        else VV_VARIANT_VALIDATOR_ENDPOINT
    )
    url = f'{endpoint}/{GenomeBuild.GRCh38.value}/{encoded_variant_description}/select'
    headers = {'content-type': 'application/json'}

    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()

    data = r.json()
    if not data:
        return None

    for value in data.values():
        if not isinstance(value, dict):
            continue

        loci = value.get('primary_assembly_loci', {})
        grch38 = loci.get('grch38')
        if not grch38:
            continue

        vcf = grch38.get('vcf')
        if not vcf:
            continue

        chrom = vcf.get('chr')
        pos = vcf.get('pos')
        ref = vcf.get('ref')
        alt = vcf.get('alt')

        if not all([chrom, pos, ref, alt]):
            continue

        # Remove "chr" prefix for gnomAD style
        chrom = chrom.replace('chr', '')
        if chrom in {'M', 'MT'}:
            chrom = 'M'

        return f'{chrom}-{pos}-{ref}-{alt}'
    return None


@function_tool
def genomic_accession_for_gene_and_transcript(
    gene_symbol: str, transcript: str
) -> Optional[dict[GenomeBuild, str]]:
    """
    Given a gene and a transcript, return a mapping of genome build -> genomic accession (NC_ ID)

    Example Output:
    {
        <GenomeBuild.GRCh37: 'GRCh37'>: 'NC_000004.11',
        <GenomeBuild.GRCh38: 'GRCh38'>: 'NC_000004.12'
    }
    """

    url = f'{VV_GENE2TRANSCRIPTSV1_ENDPOINT}/{gene_symbol}'
    headers = {'content-type': 'application/json'}

    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()

    data = r.json()
    if not data or 'transcripts' not in data:
        return None

    transcripts = data.get('transcripts', [])
    if not transcripts:
        return None

    # Pick the first transcript with genomic_spans containing NC_ accessions
    for t in transcripts:
        if t.get('reference') != transcript:
            continue
        genomic_spans = t.get('genomic_spans', {})
        if not genomic_spans:
            continue

        genome_build_map = {}
        # Filter only NC_ accessions (ignore NG_/LRG_/etc)
        nc_accessions = [acc for acc in genomic_spans if acc.startswith('NC_')]
        if not nc_accessions:
            continue

        # Sort lexicographically
        nc_accessions_sorted = sorted(nc_accessions)
        if len(nc_accessions_sorted) >= 2:
            genome_build_map[GenomeBuild.GRCh37] = nc_accessions_sorted[
                0
            ]  # smaller string
            genome_build_map[GenomeBuild.GRCh38] = nc_accessions_sorted[
                -1
            ]  # larger string
        else:
            # Only one NC_ accession — assume GRCh38 (or GRCh37 if you prefer)
            genome_build_map[GenomeBuild.GRCh38] = nc_accessions_sorted[0]

        if genome_build_map:
            return genome_build_map

    return None


@function_tool
def select_transcript(
    gene_symbol: str,
    genome_build: GenomeBuild | None,
) -> Optional[dict[str, str]]:
    """
    Select the best transcript for a gene using VariantValidator.
    If genome build is provided, passes that context to VariantValidator, if missing
    uses GRCh38

    Selection priority:
    1. MANE Select (prefer RefSeq if available)
    2. RefSeq Select
    3. Ensembl Select
    4. Longest coding sequence fallback

    Returns:
    {
        "transcript": "<accession>",
        "protein_accession": "<protein_accession>"
    }

    Returns None if no transcripts are found.
    """

    genome_build = GenomeBuild.GRCh38 if not genome_build else genome_build
    url = f'{VV_GENE2TRANSCRIPTSV2_ENDPOINT}/{gene_symbol}/select/all/{genome_build.value}'
    headers = {'content-type': 'application/json'}

    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()

    data = r.json()
    if not data or not isinstance(data, list) or 'transcripts' not in data[0]:
        return None

    transcripts = data[0]['transcripts']
    if not transcripts:
        return None

    # Rank 1: MANE + RefSeq
    for t in transcripts:
        ann = t.get('annotations', {})
        if ann.get('mane_select') and ann.get('refseq_select'):
            return {
                'transcript': t['reference'],
                'protein_accession': t.get('translation'),
            }

    # Rank 2: MANE
    for t in transcripts:
        if t.get('annotations', {}).get('mane_select'):
            return {
                'transcript': t['reference'],
                'protein_accession': t.get('translation'),
            }

    # Rank 3: RefSeq Select
    for t in transcripts:
        if t.get('annotations', {}).get('refseq_select'):
            return {
                'transcript': t['reference'],
                'protein_accession': t.get('translation'),
            }

    # Rank 4: Ensembl Select
    for t in transcripts:
        if t.get('annotations', {}).get('ensembl_select'):
            return {
                'transcript': t['reference'],
                'protein_accession': t.get('translation'),
            }

    # Rank 5: Longest CDS fallback
    def cds_length(t):
        return t.get('coding_end', 0) - t.get('coding_start', 0)

    best = max(transcripts, key=cds_length)

    return {
        'transcript': best['reference'],
        'protein_accession': best.get('translation'),
    }


VARIANT_HARMONIZATION_INSTRUCTIONS = """
System: You are an expert genomics curator and variant normalizer.

Instructions:

Using the following fields of the provided variant structure:
- gene
- transcript
- protein_accession
- genomic_accession
- genomic_coordinates
- genome_build
- rsid
- hgvs_c
- hgvs_p
- hgvs_g
- hgvs_c_inferred
- hgvs_p_inferred

normalize/canonicalize/harmonize the variant to a gnomAD style identifier aligned the GRCh38 reference genome.

Guidelines:
- If genomic_coordinates are provided, and the input explicitly contains chromosome, 1-based position, reference allele, alternate allele,
and it can directly be converted to a gnomad style id, directly resolve with the allele_registry_resolver tool.
    - Confirm the converion (e.g. chr1:55051215 G>A -> 1-55051215-G-A) before passing to allele_registry_resolver.
    - This excludes transcripts, rsIDs, HGVS (including g.), any biological lookup, any coordinate projection.
- If rsid OR caid is provided, proceed directly to the allele_registry_resolver tool and return the result.
- If both hgvs_g and a genomic accession are provided, use the gnomad_style_id_from_variant_validator tool directly, 
    passing in hgvsg in combination with genomic accession.
    - If hgvs_g contains a genomic accession (e.g., starts with NC_), use it directly.
- If hgvs_g is provided but the genomic accession is missing, use the genomic_accession_for_gene_and_transcript tool.
    - If the transcript is missing, first fetch the canonical transcript for the gene using the select_transcript tool.
- Call select_transcript if projection via VariantValidator is required and no transcript/protein context exists.
- Use the gnomad_style_id_from_variant_validator tool to attempt to map and normalize hgvsc w/ transcript OR hgvsp w/ protein accession if the first fails.
    - Note that transcript may be present in both the transcript field and the hgvs; when this happens use just the hgvs
- If hgvs_c or hgvs_p is missing, fall back to hgvs_c_inferred or hgvs_p_inferred respectively.
- The allele_registry_resolver tool should be used as a final step to output all required fields.
    - If all input arguments are None skip calling the tool and return None for all expected output.
    - If the allele_registry_resolver returns None because the variant is missing from the Clingen Allele Registry, populate
    the required output fields to the best of your ability without extrapolation.
- If we are not able to provide genomic accession, transcript, or protein as context to the gnomad_style_id_from_variant_validator
tool when constructing the variant description, return None for all expected output.
- When using the gnomad_style_id_from_variant_validator tool, note that the function argument requires combining one of the pairs
of (genomic_accession, hgvs_g), (transcript, hgvs_c), (protein_accession, hgvs_p).  You are free to infer the best possible 
approach to combine the two elements, accounting for the potential that the accession may be present multiple times.

Please Provided a precise step-by-step description of the logical flow here; any inferences, tool calls, projection inferences etc.  For example:

Input genomic_coordinates was 'chr1:55051215 G>A', and because chromosome, position, reference, and alt are supplied
we can directly convert to a gnomad style id.  We then call allele_registry_resolver and return:


```
{'gnomad_style_coordinates': '1-55051215-G-GA',
 'rsid': 'rs527413419',
 'caid': 'CA871474',
 'hgvsc': 'NM_174936.4:c.524-1063_524-1062insA',
 'hgvsg': 'NC_000001.11:g.55051215_55051216insA',
 'hgvsp': 'NP_777596.2:n.524-1063_524-1062insA'}
 ```

"""


class NormalizedVariant(BaseModel):
    gnomad_style_coordinates: Optional[str]
    rsid: Optional[str]
    caid: Optional[str]
    hgvs_c: Optional[str]
    hgvs_p: Optional[str]
    hgvs_g: Optional[str]
    normalization_confidence: Literal['high', 'medium', 'low']
    normalization_notes: Optional[str]


agent = Agent(
    name='variant_canonicalizer',
    instructions=VARIANT_HARMONIZATION_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=NormalizedVariant,
    tools=[
        select_transcript,
        genomic_accession_for_gene_and_transcript,
        allele_registry_resolver,
        gnomad_style_id_from_variant_validator,
    ],
)

from agents import Runner

result = Runner.run_sync(
    agent,
    f"""Variant: {{
      "gene": "ITPR3",
      "transcript": "NM_002224.4",
      "variant_verbatim": "c.1843G > A (p.Val615Met) in exon 16 of ITPR3 (NM_002224.4)",
      "genomic_coordinates": null,
      "hgvs_c": "c.1843G > A",
      "hgvs_p": "p.Val615Met",
      "hgvs_c_inferred": null,
      "hgvs_p_inferred": null,
      "hgvs_inference_confidence": null,
      "hgvs_inference_evidence_context": null,
      "variant_type": "missense",
      "zygosity": "heterozygous",
      "inheritance": "dominant",
      "variant_type_evidence_context": null,
      "variant_evidence_context": "c.1843G > A (p.Val615Met) in exon 16 of ITPR3 (NM_002224.4)",
      "zygosity_evidence_context": "Exome sequencing identified a heterozygous ITPR3 p.Val615Met variant segregating with the disease.",
      "inheritance_evidence_context": "In this study, we provide confirmatory evidence of the association of ITPR3 with CMT. We introduce a CMT family with autosomal dominant mutation and one case with de novo mutation in ITPR3."
    }}""",
)
