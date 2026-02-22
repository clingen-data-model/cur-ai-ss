import re
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Tuple
from urllib.parse import quote

import requests
from agents import Agent, function_tool
from pydantic import BaseModel

from lib.agents.variant_extraction_agent import GenomeBuild, VariantExtractionOutput
from lib.evagg.utils.environment import env

CLINGEN_ALLELE_REGISTRY_ENDPOINT = 'https://reg.genome.network'
EUTILS_BASE = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'
SPDI_TO_HGVS_BASE = 'https://api.ncbi.nlm.nih.gov/variation/v0/spdi'
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
def clinvar_lookup(query: str) -> List[Dict[str, Any]]:
    """
    Search ClinVar and return structured info for each matching record:
        - hgvs
        - caid (ClinGen Allele ID)
        - rsid (dbSNP rsID)

    Example query:
        "BRCA1 AND (Arg157Ser OR p.Arg157Ser OR R157S)"
    """

    headers = {'content-type': 'application/json'}

    # ---------------------
    # Step 1: ESearch
    # ---------------------
    esearch_url = f'{EUTILS_BASE}/esearch.fcgi'
    esearch_params: dict[str, str | int] = {
        'db': 'clinvar',
        'term': query,
        'retmax': 100,
        'retmode': 'json',
        'sort': 'relevance',
    }

    r = requests.get(esearch_url, params=esearch_params, headers=headers, timeout=10)
    r.raise_for_status()
    search_data = r.json()

    ids = search_data.get('esearchresult', {}).get('idlist', [])
    if not ids:
        return []

    # ---------------------
    # Step 2: ESummary
    # ---------------------
    esummary_url = f'{EUTILS_BASE}/esummary.fcgi'
    esummary_params = {
        'db': 'clinvar',
        'id': ','.join(ids),
        'retmode': 'json',
    }

    r = requests.get(esummary_url, params=esummary_params, headers=headers, timeout=10)
    r.raise_for_status()
    summary_data = r.json()

    result = summary_data.get('result', {})
    uids = result.get('uids', [])

    records: List[Dict[str, Any]] = []

    for uid in uids:
        record = result.get(uid, {})
        variation_set = record.get('variation_set', [])

        for v in variation_set:
            variation_name = v.get('variation_name')

            caid = None
            rsid = None

            for xref in v.get('variation_xrefs', []):
                if xref.get('db_source') == 'ClinGen':
                    caid = xref.get('db_id')
                elif xref.get('db_source') == 'dbSNP':
                    db_id = xref.get('db_id')
                    if db_id:
                        rsid = f'rs{db_id}'

            records.append(
                {
                    'hgvs': variation_name,
                    'caid': caid,
                    'rsid': rsid,
                }
            )
    return records


@function_tool
def dbsnp_lookup(query: str) -> List[str]:
    """
    Search dbSNP and return genomic HGVS (HGVSg) strings
    derived deterministically from SPDI using the NCBI Variation API.
    """

    headers = {'content-type': 'application/json'}
    hgvs_results: List[str] = []

    # ---------------------
    # Step 1: ESearch
    # ---------------------
    esearch_url = f'{EUTILS_BASE}/esearch.fcgi'
    esearch_params: dict[str, str | int] = {
        'db': 'snp',
        'term': query,
        'retmax': 50,
        'retmode': 'json',
        'sort': 'relevance',
    }

    r = requests.get(esearch_url, params=esearch_params, headers=headers, timeout=10)
    r.raise_for_status()
    search_data = r.json()

    ids = search_data.get('esearchresult', {}).get('idlist', [])
    if not ids:
        return []

    # ---------------------
    # Step 2: ESummary
    # ---------------------
    esummary_url = f'{EUTILS_BASE}/esummary.fcgi'
    esummary_params = {
        'db': 'snp',
        'id': ','.join(ids),
        'retmode': 'json',
    }

    r = requests.get(esummary_url, params=esummary_params, headers=headers, timeout=10)
    r.raise_for_status()
    summary_data = r.json()

    results = summary_data.get('result', {})
    uids = results.get('uids', [])

    # ---------------------
    # Step 3: Extract SPDI + Convert to HGVS
    # ---------------------
    for uid in uids:
        record = results.get(uid, {})
        spdi = record.get('spdi')
        if not spdi:
            continue

        try:
            variation_url = f'{SPDI_TO_HGVS_BASE}/{spdi}/hgvs'
            vr = requests.get(variation_url, timeout=10)
            vr.raise_for_status()
            variation_data = vr.json()

            hgvs = variation_data.get('data', {}).get('hgvs')
            if hgvs:
                hgvs_results.append(hgvs)

        except requests.RequestException:
            # Skip failures but continue processing remaining records
            continue

    return hgvs_results


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

    if isinstance(data, list):
        data = data[0]

    # -----------------------
    # CAID
    # -----------------------
    resolved_caid = None
    allele_id_url = data.get('@id')
    if allele_id_url:
        resolved_caid = allele_id_url.rstrip('/').split('/')[-1]

    # -----------------------
    # gnomAD-style (derived from genomicAlleles)
    # -----------------------
    resolved_gnomad = None

    genomic_alleles = data.get('genomicAlleles', [])

    def build_gnomad_id(g: dict[str, Any]) -> str | None:
        coords = g.get('coordinates', [])
        if not coords:
            return None

        coord = coords[0]

        chrom = g.get('chromosome')
        pos = coord.get('end')  # 1-based position
        ref = coord.get('referenceAllele')
        alt = coord.get('allele')

        if not all([chrom, pos, ref, alt]):
            return None

        return f'{chrom}-{pos}-{ref}-{alt}'

    # Prefer GRCh38
    for g in genomic_alleles:
        if g.get('referenceGenome') == 'GRCh38':
            resolved_gnomad = build_gnomad_id(g)
            if resolved_gnomad:
                break

    # Fallback to first available genome
    if not resolved_gnomad:
        for g in genomic_alleles:
            resolved_gnomad = build_gnomad_id(g)
            if resolved_gnomad:
                break

    # -----------------------
    # rsID
    # -----------------------
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

    for g in genomic_alleles:
        if g.get('referenceGenome') == 'GRCh38':
            hgvs_list = g.get('hgvs', [])
            if hgvs_list:
                resolved_hgvsg = hgvs_list[0]
                break

    if not resolved_hgvsg:
        for g in genomic_alleles:
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
            refseq_nuc = mane.get('nucleotide', {}).get('RefSeq', {}).get('hgvs')
            refseq_pro = mane.get('protein', {}).get('RefSeq', {}).get('hgvs')

            if refseq_nuc:
                resolved_hgvsc = refseq_nuc
            if refseq_pro:
                resolved_hgvsp = refseq_pro

            found_mane = True
            continue

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
def select_canonical_transcript(
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
    def cds_length(t: dict[Any, Any]) -> int:
        return t.get('coding_end', 0) - t.get('coding_start', 0)

    best = max(transcripts, key=cds_length)

    return {
        'transcript': best['reference'],
        'protein_accession': best.get('translation'),
    }


VARIANT_HARMONIZATION_INSTRUCTIONS = """
System: You are an expert genomics curator and deterministic variant normalizer.

You must follow the state machine below strictly.
You may not skip states.
You may not revisit a previous state except where explicitly allowed.
You may not call clinvar_lookup more than once for each attempted variant.
You may not call dbsnp_lookup more than once per variant.
You should not need to call select_canonical_transcript for the gene more than once per genome build.
You should not need to call genomic_accession_for_gene_and_transcript more than once per gene and transcript.

Goal:
Normalize each of the provided variants to a GRCh38 gnomAD-style identifier and resolve via
allele_registry_resolver as the final step whenever possible.

============================================================
STATE 0 — INITIAL DATA ASSESSMENT
============================================================

Use the following fields of the provided structured input:
- gene (required)
- transcript
- protein_accession
- genomic_accession
- genomic_coordinates
- genome_build
- rsid
- caid
- hgvs_c
- hgvs_p
- hgvs_g
- hgvs_c_inferred
- hgvs_p_inferred

If hgvs_c is missing → use hgvs_c_inferred if present.
If hgvs_p is missing → use hgvs_p_inferred if present.

Proceed to State 1.

============================================================
STATE 1 — DIRECT GENOMIC COORDINATE RESOLUTION
============================================================

Condition:
Input contains EXPLICIT genomic_coordinates with:
    chromosome, 1-based position, ref allele, alt allele.

Action:
1. Convert to gnomAD-style format:
    chr1:55051215 G>A → 1-55051215-G-A
    Remove "chr"
    Normalize MT → M

2. Call allele_registry_resolver using:
    gnomad_style_coordinates

3. RETURN result.

If not eligible → proceed to State 2.

============================================================
STATE 2 — IDENTIFIER RESOLUTION
============================================================

Condition:
rsid OR caid present in input.

Action:
Call allele_registry_resolver using available identifier.

RETURN result.

If neither present → proceed to State 3.

============================================================
STATE 3 — GENOMIC HGVS PROJECTION
============================================================

Condition:
hgvs_g present.

Action:

A) If hgvs_g already contains genomic accession (e.g., starts with NC_):
    Call gnomad_style_id_from_variant_validator using hgvs_g directly.

B) If genomic_accession missing:
    If transcript missing:
        Call select_canonical_transcript(gene, genome_build or GRCh38 default)
    Then Call genomic_accession_for_gene_and_transcript to retrieve genomic accession using either
    the provided or the selected transcript.

    If genomic accession still unavailable:
        FAIL → return None outputs (low confidence).

C) Construct:
    genomic_accession + ":" + hgvs_g

Call gnomad_style_id_from_variant_validator.

If successful:
    → Call allele_registry_resolver
    → RETURN result.

If unsuccessful:
    → Proceed to State 4.

============================================================
STATE 4 — TRANSCRIPT-BASED PROJECTION
============================================================

Condition:
hgvs_c OR hgvs_p available.

Definition:
A transcript or protein accession is considered valid for projection
ONLY if it contains a version suffix (e.g., NM_000059.3, ENST00000357654.9, NP_000050.2).
Unversioned accessions must not be used for projection.

------------------------------------------------------------
Step 4A — Transcript-based projection (preferred)
------------------------------------------------------------

If hgvs_c available:

    1. If transcript missing OR transcript lacks a version:
        Call select_canonical_transcript(gene, genome_build or GRCh38 default)
        Replace transcript with returned versioned transcript.
        Record selected transcript in normalization_notes.

    2. Construct:
           transcript + ":" + hgvs_c

    3. Call gnomad_style_id_from_variant_validator.

    4. If projection fails:
        Call select_canonical_transcript again (to handle retired versions),
        replace transcript with returned versioned transcript,
        reconstruct transcript + ":" + hgvs_c,
        and retry gnomad_style_id_from_variant_validator once.

    5. If projection succeeds:
        Call allele_registry_resolver using gnomad_style_coordinates.
        RETURN result.

    6. If projection still fails:
        Proceed to Step 4B.

------------------------------------------------------------
Step 4B — Protein-based fallback
------------------------------------------------------------

If hgvs_p available:

    1. If protein_accession present AND versioned:
           Construct:
               protein_accession + ":" + hgvs_p

       Else:
           If transcript missing OR transcript lacks a version:
               Call select_canonical_transcript(gene, genome_build or GRCh38 default)
               Replace transcript with returned versioned transcript.
               Record selected transcript in normalization_notes.

           If transcript available:
               Construct:
                   transcript + ":" + hgvs_p
           Else:
               Proceed to State 5.

    2. Do NOT attempt direct VariantValidator projection for protein-only rescue.
       Instead proceed to ClinVar lookup pathway.

    3. Call clinvar_lookup according to State 5 rules.

    4. If ClinVar returns rsid or caid:
           Call allele_registry_resolver.
           RETURN result.

    5. If ClinVar lookup fails:
           Proceed to State 5.

If both transcript-based and protein-based attempts fail → proceed to State 5.

============================================================
STATE 5 — CLINVAR & DBSNP LOOKUP
============================================================

Condition:
Projection in States 3 and 4 failed.

You may call clinvar_lookup EXACTLY ONCE per variant.

Step 5A — Construct Query

If hgvs_p and hgvs_p_inferred are both missing:
    Skip ClinVar lookup and return low confidence.

Query must include:
    gene AND (
        all protein representations
    )

Include:
    hgvs_p
    hgvs_p_inferred
    3-letter format (p.Arg157Ser)
    1-letter format (p.R157S)
    Without "p." prefix

Example:
BRCA1 AND (Arg157Ser OR p.Arg157Ser OR R157S OR p.R157S)

If hgvs_p contains transcript prefix (e.g., NM_...:p.Arg157Ser),
strip transcript before constructing query.

Step 5B — Call clinvar_lookup(query)

Step 5C — Interpret Results

If multiple ClinVar records returned:
    1. Prefer record with both caid AND rsid
    2. Else prefer record with caid
    3. Else prefer record with rsid
    4. Else use first record

Case A — rsid OR caid returned:
    Call allele_registry_resolver using identifier.
    RETURN result.
    normalization_confidence = medium

Case B — Only hgvs returned:
    Extract transcript and hgvs_c from hgvs.
    Example:
        NM_007294.3(BRCA1):c.4675G>A (p.Arg1559Lys) -> NM_007294.3:c.4675G>A

    Construct transcript + ":" + hgvs_c
    Call gnomad_style_id_from_variant_validator.

    If successful:
        → Call allele_registry_resolver
        → RETURN result.
        normalization_confidence = medium

    If unsuccessful:
        → RETURN None outputs.
        normalization_confidence = low

Case C — No ClinVar records:

    If hgvs_p OR hgvs_p_inferred present:

        Call dbsnp_lookup using the same query string
        that was constructed for ClinVar.

        If dbsnp_lookup returns genomic HGVS (hgvs_g):

            For each returned hgvs_g:
                Call gnomad_style_id_from_variant_validator
                using hgvs_g directly.

                If successful:
                    Call allele_registry_resolver
                    RETURN result.
                    normalization_confidence = medium

    If dbsnp_lookup returns no usable results:
        RETURN None outputs.
        normalization_confidence = low


You may NOT call clinvar_lookup again while resolving this variant.

============================================================
STATE 6 — FINALIZATION
============================================================

If allele_registry_resolver returned:
    gnomad_style_coordinates
    rsid
    caid
    hgvs_c
    hgvs_g
    hgvs_p

Return those fields.

Confidence Levels:

high:
    - Direct genomic coordinate conversion
    - rsid/caid direct resolution
    - Successful VariantValidator projection

medium:
    - Any resolution achieved via ClinVar or dbSNP lookup pathways

low:
    - Partial recovery only
    - No resolution possible

============================================================
NORMALIZATION NOTES REQUIREMENT
============================================================

You must populate normalization_notes with a clear, human-readable
summary of the normalization path taken.

Rules:
- Use short declarative sentences.
- Describe only actions actually performed.
- Output each step in-order, numerically (e.g. 1. "step" ), new line delimited.
- Please include the query arguments to the tool calls in the usage descriptions.
- Do not include internal reasoning.
- Do not reference state numbers.
- Do not speculate.
- Mention tools used (VariantValidator, ClinVar, ClinGen Allele Registry).
- If canonical transcript selection occurred, mention which transcript was selected.
- If ClinVar or dbSNP were used, explicitly state this.
- If resolution failed, clearly state that no registry match was found.
"""


class HarmonizedVariant(BaseModel):
    gnomad_style_coordinates: Optional[str]
    rsid: Optional[str]
    caid: Optional[str]
    hgvs_c: Optional[str]
    hgvs_p: Optional[str]
    hgvs_g: Optional[str]
    normalization_confidence: Literal['high', 'medium', 'low']
    normalization_notes: Optional[str]


class VariantHarmonizationOutput(BaseModel):
    variants: List[HarmonizedVariant]


agent = Agent(
    name='variant_canonicalizer',
    instructions=VARIANT_HARMONIZATION_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=VariantHarmonizationOutput,
    tools=[
        select_canonical_transcript,
        genomic_accession_for_gene_and_transcript,
        allele_registry_resolver,
        gnomad_style_id_from_variant_validator,
        clinvar_lookup,
        dbsnp_lookup,
    ],
)
