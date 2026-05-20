import hashlib
import json
import re
from enum import Enum
from functools import wraps
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
)
from urllib.parse import quote

import requests
from agents import Agent, function_tool

from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
from lib.core.environment import env
from lib.models.evidence_block import ReasoningBlock
from lib.models.variant import (
    GenomeBuild,
    HarmonizedVariant,
    VariantExtractionOutput,
)

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

    if env.NCBI_API_KEY:
        esearch_params['api_key'] = env.NCBI_API_KEY
    if env.NCBI_EMAIL:
        esearch_params['email'] = env.NCBI_EMAIL

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

    if env.NCBI_API_KEY:
        esummary_params['api_key'] = env.NCBI_API_KEY
    if env.NCBI_EMAIL:
        esummary_params['email'] = env.NCBI_EMAIL

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

    if env.NCBI_API_KEY:
        esearch_params['api_key'] = env.NCBI_API_KEY
    if env.NCBI_EMAIL:
        esearch_params['email'] = env.NCBI_EMAIL

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

    if env.NCBI_API_KEY:
        esummary_params['api_key'] = env.NCBI_API_KEY
    if env.NCBI_EMAIL:
        esummary_params['email'] = env.NCBI_EMAIL

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
    rsid: str | None = None,
    caid: str | None = None,
    hgvs_c: str | None = None,
    hgvs_g: str | None = None,
) -> Optional[list[dict[str, str | None]]]:
    """
    Resolve variant identifiers to comprehensive allele information via ClinGen Allele Registry.

    Returns a list of resolved allele records (one per unique allele in the response).
    When multiple results are returned, inspect each and select the most appropriate
    based on the context of your variant investigation.

    Query priority (tries first matching option):
    1. CAID (ClinGen Allele ID - most specific)
    2. HGVS (coding preferred over genomic)
    3. dbSNP rsID

    Each record includes:
    - rsid: dbSNP identifier if available
    - caid: ClinGen Allele ID if available
    - hgvs_c: Coding HGVS (prefer MANE Select RefSeq)
    - hgvs_g: Genomic HGVS (prefer GRCh38)
    - hgvs_p: Protein HGVS if available
    """
    if caid:
        suffix = f'allele/{quote(caid)}'
    elif hgvs_c:
        suffix = f'allele?hgvs={quote(hgvs_c)}'
    elif hgvs_g:
        suffix = f'allele?hgvs={quote(hgvs_g)}'
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

    # Normalize to list of records
    records_to_process = data if isinstance(data, list) else [data]

    results: list[dict[str, str | None]] = []

    for data in records_to_process:
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
        # Transcript HGVS (prefer MANE Select RefSeq, then RefSeq, then Ensembl)
        # -----------------------
        resolved_hgvsc = None
        resolved_hgvsp = None

        transcripts = data.get('transcriptAlleles', [])

        # Priority 1: MANE Select + RefSeq
        for t in transcripts:
            mane = t.get('MANE')
            if mane and mane.get('maneStatus') == 'MANE Select':
                refseq_nuc = mane.get('nucleotide', {}).get('RefSeq', {}).get('hgvs')
                refseq_pro = mane.get('protein', {}).get('RefSeq', {}).get('hgvs')

                if refseq_nuc:
                    resolved_hgvsc = refseq_nuc
                if refseq_pro:
                    resolved_hgvsp = refseq_pro
                break

        # Priority 2: RefSeq transcripts (NM_, NR_)
        if not resolved_hgvsc:
            for t in transcripts:
                for h in t.get('hgvs', []):
                    if ':c.' in h and (h.startswith('NM_') or h.startswith('NR_')):
                        resolved_hgvsc = h
                        break
                if resolved_hgvsc:
                    break

        # Priority 3: Any transcript with :c. (Ensembl fallback)
        if not resolved_hgvsc:
            for t in transcripts:
                for h in t.get('hgvs', []):
                    if ':c.' in h:
                        resolved_hgvsc = h
                        break
                if resolved_hgvsc:
                    break

        # Extract protein HGVS if available
        if not resolved_hgvsp:
            for t in transcripts:
                protein_hgvs = t.get('proteinEffect', {}).get('hgvs')
                if protein_hgvs:
                    resolved_hgvsp = protein_hgvs
                    break

        results.append(
            {
                'gnomad_style_coordinates': resolved_gnomad,
                'rsid': resolved_rsid or rsid,
                'caid': resolved_caid or caid,
                'hgvs_c': resolved_hgvsc,
                'hgvs_g': resolved_hgvsg,
                'hgvs_p': resolved_hgvsp,
            }
        )

    return results if results else None


@function_tool
def gnomad_style_ids_from_variant_validator(variant_description: str) -> list[str]:
    """
    Given an arbitrary variant_description (hgvsg, hgvsc, hgvsp), use VariantValidator
    to return ALL GRCh38 mapped gnomad-style variant ids.

    Example Output:
        ["1-55051215-G-GA", "1-55051214-GG-G"]
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
        return []

    ids: set[str] = set()

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

        chrom = chrom.replace('chr', '')
        if chrom in {'M', 'MT'}:
            chrom = 'M'

        ids.add(f'{chrom}-{pos}-{ref}-{alt}')

    return sorted(ids)


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
You may not call clinvar_lookup more than once.
You may not call dbsnp_lookup more than once.
You should not need to call select_canonical_transcript for the gene more than once per genome build.
You should not need to call genomic_accession_for_gene_and_transcript more than once per gene and transcript.
After allele_registry_resolver, you may call gnomad_style_ids_from_variant_validator once if needed to derive gnomad-style coordinates.
The pipeline MUST terminate after allele_registry_resolver (and optionally the follow-up VariantValidator call for gnomad coordinates).

Goal:
Normalize the provided variant to a GRCh38 gnomAD-style identifier and resolve via
allele_registry_resolver as the final step whenever possible.

If VariantValidator successfully produces a gnomAD-style ID at any stage:
    - This defines the canonical genomic representation.
    - Proceed directly to the allele_registry_resolver.
    - No further discovery steps (including ClinVar or dbSNP lookup) are allowed.

============================================================
STATE 0 — INITIAL DATA ASSESSMENT
============================================================

Use the following fields of the provided structured input:
- gene (required)
- transcript
- genomic_accession
- genomic_coordinates
- genome_build
- rsid
- caid
- hgvs_c
- hgvs_p
- hgvs_g

Proceed to State 1.

============================================================
STATE 1 — DIRECT GENOMIC RESOLUTION
============================================================

Condition:
Input contains EXPLICIT genomic_coordinates OR hgvs_g.

Action:

A) If genomic_coordinates present (chromosome, 1-based position, ref, alt):
    1. Get genomic accession:
        Call genomic_accession_for_gene_and_transcript(gene, transcript if provided) resolving with genome_build.
        If transcript missing, first call select_canonical_transcript(gene, genome_build or GRCh38).

    2. Construct full genomic HGVS:
        genomic_accession + ":g." + position + ref + ">" + alt
        Example: NC_000017.11:g.40152569C>A

B) If hgvs_g present but missing genomic accession (e.g., "17:g.40152569C>A"):
    1. Parse hgvs_g to extract coordinates (or recognize incomplete format).
    2. Get genomic accession:
        Call genomic_accession_for_gene_and_transcript(gene, transcript if available, or genome_build).
        If transcript missing, first call select_canonical_transcript(gene, genome_build or GRCh38).

    3. Reconstruct full genomic HGVS with accession:
        Example: NC_000017.11:g.40152569C>A

C) If hgvs_g already complete (starts with NC_):
    Use as-is.

D) Call allele_registry_resolver with the complete hgvs_g and genome_build.
   Do NOT pass incomplete/malformed hgvs_c or hgvs_p—the resolver will extract complete
   transcript info from the registry response.

E) If multiple results returned:
    Select the result most compatible with input context.

F) RETURN result with all available fields populated.

If neither genomic_coordinates nor hgvs_g present → proceed to State 2.

============================================================
STATE 2 — IDENTIFIER RESOLUTION
============================================================

Condition:
rsid OR caid present in input.

Action:
Call allele_registry_resolver using available identifier (caid, rsid), any available HGVS, and genome_build if known.
The resolver will prioritize CAID, then HGVS, then rsID.

If multiple results returned:
    Select the result most compatible with input context.
    Compare resolved values (hgvs_c, transcript annotations, hgvs_g) against input variant data.

RETURN selected result with all available fields populated.
NOTE: Even if allele_registry_resolver returns no match (None), still return the input
identifier (rsid or caid) with other fields set to None.

If neither present → proceed to State 3.

============================================================
STATE 3 — TRANSCRIPT-BASED PROJECTION
============================================================

Condition:
hgvs_c present.

Action

    1. If transcript missing OR unversioned:
        Call select_canonical_transcript(gene, genome_build or GRCh38 default)
        Replace transcript with returned versioned transcript.
        Record selected transcript in reasoning.

    2. Construct:
        transcript + ":" + hgvs_c

    3. Call gnomad_style_ids_from_variant_validator (may return multiple gnomAD-style IDs).
        If multiple IDs returned:
            Select the ID most compatible with input variant context (hgvs_c, hgvs_p, transcript, genomic coordinates).

    4. If projection fails:
        Retry once with select_canonical_transcript to handle retired versions.

    5. If projection succeeds:
        Call allele_registry_resolver using hgvs_c and genome_build.
        The resolver will prioritize HGVS queries, which don't depend on gnomAD presence.
            - If multiple results returned:
                - Select the result most compatible with input variant context (hgvs_c, hgvs_p, transcript, genomic coordinates).
            RETURN result with all fields populated.
            - NOTE: Even if allele_registry_resolver returns no match (None), still return with
              hgvs_c populated and other resolver fields set to None.

    6. If projection still fails:
        Proceed to State 4.

============================================================
STATE 4 — CLINVAR & DBSNP LOOKUP
============================================================

Condition:
Previous projections failed but hgvs_p is present.

You may call clinvar_lookup EXACTLY ONCE.
You may call dbsnp_lookup EXACTLY ONCE.

Step 5A — Construct Query

Query includes:
    gene AND all protein representations:
        hgvs_p
        3-letter format (p.Arg157Ser)
        1-letter format (p.R157S)
        Without "p." prefix

Examples:
    "BRCA1 AND (Arg157Ser OR p.Arg157Ser OR R157S)"
    "TP53 AND (Arg175His OR p.Arg175His OR R175H OR p.R175H)"
    "CFTR AND (Phe508del OR p.Phe508del OR F508del OR p.F508del)"


Step 5B — Call clinvar_lookup(query)

Step 5C — Interpret Results

Case A — rsid OR caid returned:
    Call allele_registry_resolver with rsid/caid, any available HGVS from ClinVar results, and genome_build.
    The resolver will prioritize CAID, then HGVS.
        - If multiple results returned:
            - Select the result most compatible with input variant context.
    RETURN result.

Case B — Only hgvs returned:
    Extract hgvs_c or hgvs_g from ClinVar results.
    If hgvs_c available:
        Call allele_registry_resolver with hgvs_c and genome_build.
    Else if hgvs_g available:
        Ensure genomic accession is present; if not, add it (see State 1).
        Call allele_registry_resolver with complete hgvs_g and genome_build.
        - If multiple results returned:
            - Select the result most compatible with input variant context.
        - RETURN selected record with all fields populated.
        - NOTE: Even if allele_registry_resolver returns no match (None), still return with
          hgvs_g populated and other resolver fields set to None.

Case C — ClinVar empty:
    Call dbsnp_lookup using EXACT SAME query.

    If dbsnp_lookup returns genomic HGVS (hgvs_g):
        Prefer hgvs_g compatible with input context.
        Ensure genomic accession is present; if not, add it (see State 1).
        Call allele_registry_resolver using complete hgvs_g and genome_build.
            - If multiple results returned:
                - Select the result most compatible with input variant context.
            - RETURN selected record with all fields populated.
            - NOTE: Even if allele_registry_resolver returns no match (None), still return with
              hgvs_g populated and other resolver fields set to None.

    If dbsnp_lookup returns no usable results:
        RETURN outputs with all normalized fields as None.

If EITHER clinvar_lookup OR dbsnp_lookup returns no results RETURN outputs with all normalized fields as None.

============================================================
STATE 5 — GNOMAD COORDINATES (POST-REGISTRY)
============================================================

After allele_registry_resolver returns:
- If gnomad_style_coordinates is NULL but hgvs_g is available:
    Call gnomad_style_ids_from_variant_validator(hgvs_g) to derive gnomad-style coordinates
    If successful, use the first ID returned.
    If call fails or returns empty, continue with null gnomad_style_coordinates.

============================================================
STATE 6 — FINALIZATION
============================================================

Return a single harmonized variant object with:
- reasoning (clear human-readable summary)
- allele_registry_resolver fields if available: rsid, caid, hgvs_c, hgvs_g, hgvs_p
- gnomad_style_coordinates if derived from VariantValidator

Confidence Levels:

high:
    - Direct genomic coordinate conversion
    - rsid/caid direct resolution
    - Successful VariantValidator projection

medium:
    - Resolution via ClinVar or dbSNP lookup
    - Derived gnomAD coordinates via VariantValidator post-processing

low:
    - Partial recovery only
    - No resolution possible

============================================================
REASONING REQUIREMENT
============================================================

- Populate reasoning with a clear, human-readable summary.
- Short declarative sentences, numerically ordered.
- Include query arguments to tool calls.
- Mention tools used (VariantValidator, ClinVar, ClinGen Allele Registry).
- Mention canonical transcript selection if it occurred.
- Explicitly mention ClinVar or dbSNP usage.
- If resolution failed, clearly state no registry match found.
"""


VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS = VARIANT_HARMONIZATION_INSTRUCTIONS

agent = Agent(
    name='variant_harmonizer',
    instructions=BASE_SYSTEM_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=ReasoningBlock[HarmonizedVariant],
    tools=[
        select_canonical_transcript,
        genomic_accession_for_gene_and_transcript,
        allele_registry_resolver,
        gnomad_style_ids_from_variant_validator,
        clinvar_lookup,
        dbsnp_lookup,
    ],
)
