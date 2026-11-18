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
from lib.agents.core_extraction_rules import FLAG_RULES
from lib.agents.model_facing import model_facing_output
from lib.agents.model_factory import extraction_model, extraction_model_settings
from lib.agents.variant_annotation_agent import _get_session_with_retries
from lib.core.environment import env
from lib.models.evidence_block import ReasoningBlock
from lib.models.flag import FlaggedReasoningBlock
from lib.models.variant import (
    GenomeBuild,
    HarmonizedVariant,
    VariantExtractionOutput,
    well_formed_caid,
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
        - hgvs (ClinVar's title, e.g. "NM_002448.3(MSX1):c.605G>C (p.Arg202Pro)")
        - caid (ClinGen Allele ID)
        - rsid (dbSNP rsID)
        - protein_change (ClinVar's own one-letter form, e.g. "R202P")
        - aliases (other names the record is known by, e.g. legacy or
          domain-relative numbering such as "R31P")
        - condition (trait names from the germline classification)
        - classification (e.g. "Pathogenic")

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

    session = _get_session_with_retries()
    r = session.get(esearch_url, params=esearch_params, headers=headers, timeout=10)
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

    r = session.get(esummary_url, params=esummary_params, headers=headers, timeout=10)
    r.raise_for_status()
    return _clinvar_records(r.json())


def _clinvar_records(summary_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten an esummary reply into one record per variation.

    Beyond the identifiers, this keeps the names ClinVar knows the variation
    by. A paper's protein change often uses numbering that differs from the
    RefSeq isoform ClinVar names (a residue counted within a domain, an older
    isoform), and ClinVar records that history in ``aliases`` and
    ``protein_change``; without them the agent sees only a codon that does
    not match and wrongly rejects a record its own query found.
    """
    result = summary_data.get('result', {})
    uids = result.get('uids', [])

    records: List[Dict[str, Any]] = []

    for uid in uids:
        record = result.get(uid, {})
        classification = record.get('germline_classification') or {}
        condition = [
            t.get('trait_name')
            for t in classification.get('trait_set', []) or []
            if t.get('trait_name')
        ]
        for v in record.get('variation_set', []):
            caid = None
            rsid = None

            for xref in v.get('variation_xrefs', []):
                if xref.get('db_source') == 'ClinGen':
                    caid = well_formed_caid(xref.get('db_id'))
                elif xref.get('db_source') == 'dbSNP':
                    db_id = xref.get('db_id')
                    if db_id:
                        rsid = f'rs{db_id}'

            records.append(
                {
                    'hgvs': v.get('variation_name'),
                    'caid': caid,
                    'rsid': rsid,
                    'protein_change': record.get('protein_change') or None,
                    'aliases': list(v.get('aliases') or []),
                    'condition': condition,
                    'classification': classification.get('description') or None,
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
    session = _get_session_with_retries()

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

    r = session.get(esearch_url, params=esearch_params, headers=headers, timeout=10)
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

    r = session.get(esummary_url, params=esummary_params, headers=headers, timeout=10)
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
            vr = session.get(variation_url, timeout=10)
            vr.raise_for_status()
            variation_data = vr.json()

            hgvs = variation_data.get('data', {}).get('hgvs')
            if hgvs:
                hgvs_results.append(hgvs)

        except requests.RequestException:
            # Skip failures but continue processing remaining records
            continue

    return hgvs_results


def _registry_query(
    rsid: str | None,
    caid: str | None,
    hgvs_c: str | None,
    hgvs_g: str | None,
) -> str | None:
    """The Allele Registry path to ask: CAID, then coding HGVS, then genomic
    HGVS, then rsID; None when there is nothing to ask with."""
    # Only a registry ID goes to allele/<id>. Anything else in the CAID field
    # (extraction has put ClinVar submission accessions there) is an HTTP 4xx
    # or 5xx from the registry, and since it outranks the HGVS, the HGVS was
    # never tried.
    caid = well_formed_caid(caid)
    if caid:
        return f'allele/{quote(caid)}'
    if hgvs_c:
        return f'allele?hgvs={quote(hgvs_c)}'
    if hgvs_g:
        return f'allele?hgvs={quote(hgvs_g)}'
    if rsid:
        return f'alleles?dbSNP.rs={quote(rsid)}'
    return None


def _registry_gnomad_id(genomic_allele: dict[str, Any]) -> str | None:
    """CHROM-POS-REF-ALT for one of the Allele Registry's genomic alleles.

    The registry's coordinates count the gaps between bases, so ``start`` is
    the 0-based start and the first changed base is ``start + 1``. ``end`` was
    used until 2026-11-18, which is right for a single base and names the
    last base of anything longer: B2M's CC>TT at 44715509-44715510 came out
    as 15-44715510-CC-TT, whose REF the genome does not have there.

    An insertion or deletion has an empty REF or ALT, and a VCF needs the base
    before it as an anchor, which the registry does not give; those get None
    and come from VariantValidator instead.
    """
    coords = genomic_allele.get('coordinates', [])
    if not coords:
        return None
    coord = coords[0]
    chrom = genomic_allele.get('chromosome')
    start = coord.get('start')
    ref = coord.get('referenceAllele')
    alt = coord.get('allele')
    if not chrom or start is None or not ref or not alt:
        return None
    return f'{chrom}-{start + 1}-{ref}-{alt}'


def _registry_protein_hgvs(hgvs: str | None) -> str | None:
    """The registry's protein description, if it is one.

    For a change with no protein consequence it can name, such as a splice
    site change, the registry puts the nucleotide change on the protein
    accession (``NP_001735.1:n.387-1G>A`` for CAMK4 c.387-1G>A), which was
    stored as the variant's hgvs_p on 15 dev variants.
    """
    if hgvs and ':p.' in hgvs:
        return hgvs
    return None


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
    suffix = _registry_query(rsid, caid, hgvs_c, hgvs_g)
    if suffix is None:
        return None

    url = f'{CLINGEN_ALLELE_REGISTRY_ENDPOINT}/{suffix}'
    headers = {'content-type': 'application/json'}
    session = _get_session_with_retries()

    r = session.get(url, headers=headers, timeout=10)
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
            resolved_caid = well_formed_caid(allele_id_url.rstrip('/').split('/')[-1])

        # -----------------------
        # gnomAD-style (derived from genomicAlleles)
        # -----------------------
        resolved_gnomad = None

        genomic_alleles = data.get('genomicAlleles', [])

        # Prefer GRCh38
        for g in genomic_alleles:
            if g.get('referenceGenome') == 'GRCh38':
                resolved_gnomad = _registry_gnomad_id(g)
                if resolved_gnomad:
                    break

        # Fallback to first available genome
        if not resolved_gnomad:
            for g in genomic_alleles:
                resolved_gnomad = _registry_gnomad_id(g)
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

        # Helper to extract and sort by transcript version (e.g., NM_006513.4 > NM_006513.3)
        def extract_version(hgvs_str: str) -> tuple[str, int]:
            parts = hgvs_str.split(':')[0]
            if '.' in parts:
                acc, ver = parts.rsplit('.', 1)
                try:
                    return (acc, int(ver))
                except ValueError:
                    return (parts, 0)
            return (parts, 0)

        # Priority 1: MANE Select + RefSeq
        for t in transcripts:
            mane = t.get('MANE')
            if mane and mane.get('maneStatus') == 'MANE Select':
                refseq_nuc = mane.get('nucleotide', {}).get('RefSeq', {}).get('hgvs')
                refseq_pro = mane.get('protein', {}).get('RefSeq', {}).get('hgvs')

                if refseq_nuc:
                    resolved_hgvsc = refseq_nuc
                resolved_hgvsp = _registry_protein_hgvs(refseq_pro)
                break

        # Priority 2: RefSeq transcripts (NM_, NR_) - prefer latest version
        if not resolved_hgvsc:
            refseq_candidates = []
            for t in transcripts:
                for h in t.get('hgvs', []):
                    if ':c.' in h and (h.startswith('NM_') or h.startswith('NR_')):
                        refseq_candidates.append(h)

            if refseq_candidates:
                refseq_candidates.sort(key=extract_version, reverse=True)
                resolved_hgvsc = refseq_candidates[0]

        # Priority 3: Any transcript with :c. (Ensembl fallback) - prefer latest version
        if not resolved_hgvsc:
            ensembl_candidates = []
            for t in transcripts:
                for h in t.get('hgvs', []):
                    if ':c.' in h:
                        ensembl_candidates.append(h)

            if ensembl_candidates:
                ensembl_candidates.sort(key=extract_version, reverse=True)
                resolved_hgvsc = ensembl_candidates[0]

        # Extract protein HGVS if available
        if not resolved_hgvsp:
            for t in transcripts:
                protein_hgvs = _registry_protein_hgvs(
                    t.get('proteinEffect', {}).get('hgvs')
                )
                if protein_hgvs:
                    resolved_hgvsp = protein_hgvs
                    break

        results.append(
            {
                'gnomad_style_coordinates': resolved_gnomad,
                'rsid': resolved_rsid or rsid,
                'caid': resolved_caid or well_formed_caid(caid),
                'hgvs_c': resolved_hgvsc,
                'hgvs_g': resolved_hgvsg,
                'hgvs_p': resolved_hgvsp,
            }
        )

    return results if results else None


def _variant_validator_projection(data: dict[str, Any]) -> dict[str, list[str]]:
    """The GRCh38 gnomAD-style ids in a VariantValidator reply, and its warnings.

    The warnings are the only place VariantValidator says why it produced no
    id: "Variant reference (T) does not agree with reference sequence (C)",
    "does not correspond with an exon boundary". Until 2026-11-18 only the
    ids were passed on, so the agent saw an empty list, could not tell a
    rejected description from a lookup failure, and stored descriptions
    VariantValidator had rejected (EDAR c.1056T>C, TSEN2 c.914-5T>A). LOVD's
    syntax-check lines repeat the same verdict and are left out.
    """
    ids: set[str] = set()
    warnings: list[str] = []
    for value in data.values():
        if not isinstance(value, dict):
            continue
        for warning in value.get('validation_warnings', []):
            if not warning.startswith('Lovd') and warning not in warnings:
                warnings.append(warning)
        vcf = value.get('primary_assembly_loci', {}).get('grch38', {}).get('vcf')
        if not vcf:
            continue
        chrom, pos, ref, alt = (vcf.get(k) for k in ('chr', 'pos', 'ref', 'alt'))
        if not all([chrom, pos, ref, alt]):
            continue
        chrom = chrom.replace('chr', '')
        if chrom in {'M', 'MT'}:
            chrom = 'M'
        ids.add(f'{chrom}-{pos}-{ref}-{alt}')
    return {'gnomad_ids': sorted(ids), 'validation_warnings': warnings}


@function_tool
def gnomad_style_ids_from_variant_validator(
    variant_description: str,
) -> dict[str, list[str]]:
    """
    Given an arbitrary variant_description (hgvsg, hgvsc, hgvsp), use VariantValidator
    to return ALL GRCh38 mapped gnomad-style variant ids, with VariantValidator's
    validation warnings. With no ids, the warnings say why: a reference mismatch
    or an exon boundary error means the description is not valid on that
    transcript. A warning can also come with ids, such as a description
    VariantValidator corrected before mapping it.

    Example Output:
        {"gnomad_ids": ["1-55051215-G-GA", "1-55051214-GG-G"], "validation_warnings": []}
    """
    return _validate_with_variant_validator(variant_description)


def _validate_with_variant_validator(variant_description: str) -> dict[str, list[str]]:
    """VariantValidator's GRCh38 gnomAD-style ids and warnings for a description."""
    encoded_variant_description = quote(variant_description, safe='')
    endpoint = (
        VV_VARIANT_VALIDATOR_ENSEMBL_ENDPOINT
        if variant_description.strip().startswith(('ENST', 'ENSP', 'ENSG'))
        else VV_VARIANT_VALIDATOR_ENDPOINT
    )
    url = f'{endpoint}/{GenomeBuild.GRCh38.value}/{encoded_variant_description}/select'
    headers = {'content-type': 'application/json'}
    session = _get_session_with_retries()

    r = session.get(url, headers=headers, timeout=10)
    r.raise_for_status()

    data = r.json()
    if not data:
        return {'gnomad_ids': [], 'validation_warnings': []}
    return _variant_validator_projection(data)


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
    session = _get_session_with_retries()

    r = session.get(url, headers=headers, timeout=10)
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

        genome_build_map = _builds_of_chromosome_accessions(list(genomic_spans))
        if genome_build_map:
            return genome_build_map

    return None


def _builds_of_chromosome_accessions(accessions: list[str]) -> dict[GenomeBuild, str]:
    """GRCh37 and GRCh38 for a transcript's chromosome accessions.

    GRCh38 is the higher version of the chromosome's NC_ accession. The
    versions were compared as text until 2026-11-18, where NC_000018.10 sorts
    before NC_000018.9, so on chromosomes 5, 11, 15, 16, 18, 19 and Y (whose
    version goes from one digit to two between the builds) the two came back
    swapped: the agent was told chr18's GRCh38 accession was NC_000018.9 and
    wrote NC_000018.11, which does not exist, or believed it and wrote
    APOA1's change on GRCh37's NC_000011.9. NG_, LRG_ and other non-chromosome
    accessions are ignored; a single NC_ accession is taken as GRCh38.
    """

    def version(accession: str) -> int:
        _, _, number = accession.rpartition('.')
        return int(number) if number.isdigit() else 0

    nc_accessions = sorted(
        (acc for acc in accessions if acc.startswith('NC_')), key=version
    )
    if not nc_accessions:
        return {}
    if len(nc_accessions) == 1:
        return {GenomeBuild.GRCh38: nc_accessions[0]}
    return {
        GenomeBuild.GRCh37: nc_accessions[0],
        GenomeBuild.GRCh38: nc_accessions[-1],
    }


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
    session = _get_session_with_retries()

    r = session.get(url, headers=headers, timeout=10)
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


@function_tool
def resolve_transcript_version(transcript: str) -> Optional[dict[str, str]]:
    """
    Resolve an unversioned (or any) transcript to the most recent supported version
    of that SAME base accession using VariantValidator. Use this to preserve the
    transcript reported in the paper instead of substituting the gene's canonical
    transcript, since coding (c.) coordinates are transcript-specific.

    Example: "NM_000000" -> {"transcript": "NM_000000.4", "protein_accession": "NP_000000.2"}

    Returns None if the base accession is not supported by VariantValidator (e.g. a
    retired transcript); callers should fall back to select_canonical_transcript.
    """

    base = transcript.split('.')[0]
    if not base:
        return None

    url = f'{VV_GENE2TRANSCRIPTSV1_ENDPOINT}/{base}'
    headers = {'content-type': 'application/json'}
    session = _get_session_with_retries()

    r = session.get(url, headers=headers, timeout=10)
    r.raise_for_status()

    data = r.json()
    transcripts = data.get('transcripts', []) if isinstance(data, dict) else []
    if not transcripts:
        return None

    # Keep only references for the same base accession, then pick the highest version.
    best_version = -1
    best: Optional[dict[str, str]] = None
    for t in transcripts:
        reference = t.get('reference', '')
        ref_base, _, ref_version = reference.partition('.')
        if ref_base != base or not ref_version.isdigit():
            continue
        version = int(ref_version)
        if version > best_version:
            best_version = version
            best = {
                'transcript': reference,
                'protein_accession': t.get('translation'),
            }

    return best


# The most transcripts transcripts_fitting_description sends to
# VariantValidator, one request each to its public API.
MAX_TRANSCRIPTS_TRIED = 20

# VariantValidator warnings that mean the description, as written, is not on
# the transcript: the bases it states are not there, its intronic offset is
# not counted from an exon edge, or VariantValidator rewrote it to make it fit.
_REJECTION_MARKERS = (
    'ReferenceMismatchError',
    'IntronBaseMismatchWarning',
    'ExonBoundaryError',
    'OutOfBoundsError',
    'automapped to',
)


def _fits_as_written(validation: dict[str, list[str]]) -> bool:
    """Whether VariantValidator mapped the description without changing it."""
    return bool(validation['gnomad_ids']) and not any(
        marker in warning
        for warning in validation['validation_warnings']
        for marker in _REJECTION_MARKERS
    )


def _coding_transcripts(gene_transcripts: Any) -> list[str]:
    """The coding RefSeq transcripts in a gene2transcripts reply, every version,
    in the order VariantValidator lists them."""
    if not isinstance(gene_transcripts, dict):
        return []
    return [
        t['reference']
        for t in gene_transcripts.get('transcripts', [])
        if t.get('reference', '').startswith('NM_')
        and t.get('coding_start') is not None
    ]


@function_tool
def transcripts_fitting_description(gene_symbol: str, hgvs_c: str) -> dict[str, Any]:
    """
    Find a transcript of the gene that a coding change fits, when the one
    tried rejected it. Lists every coding RefSeq transcript of the gene, every
    version VariantValidator holds, and tries the change on each in turn,
    stopping at the first VariantValidator accepts unchanged.

    hgvs_c: the change as the paper numbers it, with or without an accession
    ("c.914-5T>A").

    Returns:
    {
      "fitting": {"transcript", "gnomad_ids", "validation_warnings"} or null,
      "rejected": [{"transcript", "validation_warnings"}],
      "not_tried": [<accessions past the limit>]
    }
    """
    url = f'{VV_GENE2TRANSCRIPTSV1_ENDPOINT}/{quote(gene_symbol, safe="")}'
    session = _get_session_with_retries()
    r = session.get(url, headers={'content-type': 'application/json'}, timeout=10)
    r.raise_for_status()
    transcripts = _coding_transcripts(r.json())

    change = hgvs_c.split(':', 1)[-1].strip()
    rejected: list[dict[str, Any]] = []
    for transcript in transcripts[:MAX_TRANSCRIPTS_TRIED]:
        try:
            validation = _validate_with_variant_validator(f'{transcript}:{change}')
        except requests.RequestException as e:
            validation = {
                'gnomad_ids': [],
                'validation_warnings': [f'VariantValidator request failed: {e}'],
            }
        if _fits_as_written(validation):
            return {
                'fitting': {'transcript': transcript, **validation},
                'rejected': rejected,
                'not_tried': [],
            }
        rejected.append(
            {
                'transcript': transcript,
                'validation_warnings': validation['validation_warnings'],
            }
        )
    return {
        'fitting': None,
        'rejected': rejected,
        'not_tried': transcripts[MAX_TRANSCRIPTS_TRIED:],
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
The pipeline MUST terminate after allele_registry_resolver (and optionally the follow-up VariantValidator call for gnomad coordinates),
unless the consequence check of State 3 rejects what the registry returned; then the next numbering candidate, or State 4, follows.

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

Notation in these fields is sometimes wrong in a way the paper itself is not.
It was read out of a PDF, and a text layer can declare the wrong character for a
glyph, drop one, split a token with a stray space, or merge two together. Which
character goes wrong depends on the document's fonts, so there is no fixed list
to check against: an operator arriving as a digit is one form ("c.98T 4G" or
"c.3733T4G" for "c.98T>G"), a superscript or minus sign lost from a position is
another. Separately, older papers are written to older conventions -- the
reference base ahead of the position, "c.C2665G" for "c.2665C>G" -- which is not
corruption but still is not HGVS.

So when a c./g./p. string does not read as valid HGVS, that is evidence about
how the text reached you, not evidence that the variant cannot be resolved. Work
out what the paper meant and continue with that reading, within two limits: use
only the characters already present, never inventing a change the paper does not
state, and never return the unreadable string as your answer. The lookups are
the check -- a reading that is wrong will not resolve, which is the signal to
try another one rather than to stop.

Numbering check. Older papers may count nucleotides from the first base of a
GenBank mRNA rather than from the ATG, so every position runs ahead of HGVS c.
by the 5' UTR; a GenBank accession (X12345) in transcript is a sign of it. When
both a coding position and a residue are known, check one against the other:
residue N is encoded by c.(3N-2) to c.3N, so "c.598C>T" with "Arg200Ter" fits
and "C810T" with "R200X" does not. A position outside the window is not a c.
coordinate and is not projected as written -- the reference base can match by
chance, and the string then resolves cleanly to a different allele; State 3
says what to project instead. A position with no residue to check against on a
GenBank-numbered transcript is not projected at all: State 4 if there is a
protein change, else every normalized field null and an unresolved flag.

Description inference. A variant can also arrive with every notation field
null and the variant string describing the change in words: "deletion of
exon 2", "a 4-bp deletion at codon 120", "arginine 66 replaced by
tryptophan", "IVS3+1G>A". Before leaving this state, infer the conceivable
set of terms the words could mean and carry them into the states below as if
they were the input fields they stand in for:
    - a nucleotide change with a position and bases -> hgvs_c candidates, for
      State 3 ("G to A at nucleotide 598" -> c.598G>A);
    - a protein change -> hgvs_p in its forms, for State 4 ("arginine 66 to
      tryptophan" -> p.Arg66Trp, R66W);
    - an identifier quoted in words -> rsid or caid, for State 2;
    - a change named by exons, introns or a legacy name -> the names ClinVar
      titles and aliases such changes by, as search terms for State 4
      ("deletion of exon 2" -> "exon 2 deletion", "EX2DEL"; "IVS3+1G>A" as
      written, since ClinVar keeps legacy names in aliases).
The terms carry only what the words say -- the numbers, bases and residues in
the text; an exon's bounds are not written from memory, and words about the
individual (heterozygous, homozygous, de novo, maternal) are not part of the
change. Try candidates in state order; the lookups are the check, as above.
Say in basis which terms were inferred from which words. A resolution that
rests on an inferred term rather than the paper's own notation is confidence
low; when no candidate resolves, every normalized field is null with an
unresolved flag naming the terms tried.

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

If allele_registry_resolver returns no match (None) or fails (an error, not a
result), the identifier did not resolve; it is not the end of the run. Proceed
to State 3 when the input has a coding change, then State 4 as usual, and say
in basis that the identifier did not resolve. Return the input identifier with
other fields set to None only when no later state has anything to work from.

If neither present → proceed to State 3.

============================================================
STATE 3 — TRANSCRIPT-BASED PROJECTION
============================================================

Condition:
hgvs_c present, or a coding change readable from the variant string (State 0).

Action

    Numbering. When State 0 found the paper's position outside the residue's
    window, project the window's three positions instead, each with the
    paper's bases -- "C810T" with "R200X" gives c.598C>T, c.599C>T and
    c.600C>T -- and keep the first whose consequence passes step 5; if none
    does, State 4. Say the mapping in basis ("the paper's 810 is c.598; its
    numbering runs 212 ahead").

    1. Resolve a versioned transcript, preserving the paper's transcript when possible:

        a) If transcript present but UNVERSIONED (e.g. "NM_000000"):
            Call resolve_transcript_version(transcript) to upgrade it to the most
            recent supported version of the SAME base accession (e.g. "NM_000000.4").
            Coding (c.) coordinates are transcript-specific, so the paper's transcript
            MUST be preserved rather than swapped for the gene's canonical transcript.
            Replace transcript with the returned versioned transcript.
            If it returns null (base accession not supported / retired), fall back to
            select_canonical_transcript(gene, genome_build or GRCh38 default).

        b) If transcript MISSING entirely, or is a GenBank accession rather
           than a RefSeq or Ensembl one:
            Call select_canonical_transcript(gene, genome_build or GRCh38 default)
            Replace transcript with returned versioned transcript.

        Record the resolved transcript and which path was taken in basis.

    2. Construct:
        transcript + ":" + hgvs_c

    3. Call gnomad_style_ids_from_variant_validator (may return multiple gnomAD-style IDs).
        If multiple IDs returned:
            Select the ID most compatible with input variant context (hgvs_c, hgvs_p, transcript, genomic coordinates).
        With no IDs, its validation_warnings say why. A reference mismatch
        or an exon boundary error means the paper's position does not fit
        this transcript: the projection failed, and the description is not
        returned as hgvs_c on it. Quote the warning in basis.

    4. If projection fails:
        Call transcripts_fitting_description(gene, hgvs_c) once. A paper
        often numbers a change on a transcript other than the one chosen, or
        on an older version of it; the tool tries the change, as the paper
        numbers it, on each coding RefSeq transcript of the gene in turn and
        returns the first VariantValidator accepts unchanged.
        - It returns one: continue at step 5 on that transcript, with its
          gnomad_ids. If the description names no reference bases (c.123del,
          c.45dup), it fits wherever its positions exist, so the fit is no
          evidence of the transcript the paper used: flag that the
          transcript is assumed.
        - It returns none: State 4.
        Say in basis which transcript fitted, or for a rejection the warning
        VariantValidator gave.

    5. If projection succeeds:
        Call allele_registry_resolver using hgvs_c and genome_build.
        The resolver will prioritize HGVS queries, which don't depend on gnomAD presence.
            - If multiple results returned:
                - Select the result most compatible with input variant context (hgvs_c, hgvs_p, transcript, genomic coordinates).

        Consequence check. The registry's hgvs_p must sit at the paper's
        residue and name the paper's change ("=" for silent, "Ter" for a
        stop), and agree with variant_type: a Synonymous input that resolved
        to a missense consequence is not the paper's allele, nor is a
        deletion of a base other than the one the paper names. A consequence
        at the same residue differing only in kind is the same allele; keep
        it with a mismatch flag. Any other is a failed projection, whatever
        VariantValidator accepted. Do not return it with a note: try the next
        numbering candidate, else State 4. With no residue to check against,
        return the result.

            RETURN result with all fields populated.
            - NOTE: Even if allele_registry_resolver returns no match (None), still return with
              hgvs_c populated and other resolver fields set to None.

    6. If projection still fails:
        Proceed to State 4.

============================================================
STATE 4 — CLINVAR & DBSNP LOOKUP
============================================================

Condition:
Previous projections failed AND a protein change is available, either as hgvs_p
or as a protein change written into the variant string -- "C331Y", "Cys331Tyr",
"Trp66Gly" -- or State 0 inferred search terms from a description. Older papers
frequently report changes only that way, and a variant whose protein change
sits in the variant string is as searchable as one whose sits in hgvs_p: the
query below is built from the amino acids and the position, and both forms
carry them.

Do not skip this state because hgvs_p is null. That is the difference between
returning a normalized allele and returning nothing, for a whole class of paper.

You may call clinvar_lookup EXACTLY ONCE.
You may call dbsnp_lookup EXACTLY ONCE.

Step 5A — Construct Query

Query includes:
    gene AND all protein representations of the change, taken from hgvs_p where
    it is populated and from the variant string otherwise:
        hgvs_p
        3-letter format (p.Arg157Ser)
        1-letter format (p.R157S)
        Without "p." prefix

Examples:
    "BRCA1 AND (Arg157Ser OR p.Arg157Ser OR R157S)"
    "TP53 AND (Arg175His OR p.Arg175His OR R175H OR p.R175H)"
    "CFTR AND (Phe508del OR p.Phe508del OR F508del OR p.F508del)"

Terms State 0 inferred from a description take the place of the protein
forms: the gene AND the inferred names.
    "DMD AND (exon 45 deletion OR deletion of exon 45 OR EX45DEL)"
    "CFTR AND (IVS8-5T OR 5T allele)"


Step 5B — Call clinvar_lookup(query)

Step 5C — Interpret Results

A record ClinVar returned for your query is a candidate for the SAME variant
even when its title numbers the residue differently. Papers often count
residues within a domain (the MSX1 homeodomain's Arg31 is Arg202 of the
RefSeq protein) or against an older isoform, and ClinVar keeps those names in
the record's aliases and protein_change. Before rejecting a record because
the codon does not match:
    - If the queried change (any of its forms: Arg31Pro, R31P, p.R31P) appears
      in the record's aliases or protein_change, it IS the variant. Accept it,
      proceed with Case A or B, and state the numbering mapping in basis
      ("paper's Arg31Pro is homeodomain-relative; ClinVar names the same
      change p.Arg202Pro, alias R31P").
    - If the record's condition matches the paper's disease and the gene and
      amino acids agree (same reference and substituted residue, different
      position), treat it as the same variant with the caveat stated and
      confidence low, rather than returning nothing.
    - Reject only when neither the aliases nor the amino acids support the
      match. A mismatched codon alone is not grounds for rejection when the
      record was found by the change you searched for.

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
    If successful, use the first of its gnomad_ids.
    If call fails or returns empty, continue with null gnomad_style_coordinates.

============================================================
STATE 6 — FINALIZATION
============================================================

Return a single harmonized variant object with:
- basis (clear human-readable summary)
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
    - Resolution resting on a term inferred from a description (State 0)
    - No resolution possible

============================================================
BASIS REQUIREMENT
============================================================

- Populate basis with a clear, human-readable summary written for a human curator.
- Short declarative sentences, numerically ordered.
- Lead with which resolution path was taken and why (e.g., "No genomic coordinates or rsID provided, so resolved via transcript HGVS (State 3)" or "rsID present — resolved directly via identifier lookup (State 2)"). This gives the curator an immediate sense of the harmonization approach.
- Then describe what happened at each step: which states were entered, why each was entered or skipped, and what was found.
- Include the specific identifiers and terms you searched for (e.g., "Searched ClinVar for 'BRCA1 Arg175His'").
- Mention which databases and tools you consulted and what they returned (e.g., "Called VariantValidator with NM_007294.4:c.524G>A — returned gnomAD ID 17-41246481-C-T").
- Mention canonical transcript selection if it occurred (e.g., "Selected NM_007294.4 as canonical transcript for BRCA1").
- Note whether ClinVar or dbSNP were consulted and what they returned.
- If resolution failed, clearly state which paths were tried and why none succeeded.
- Do not use Python function names (e.g., clinvar_lookup, allele_registry_resolver) — use the database or tool name instead.
"""


VARIANT_HARMONIZATION_AGENT_INSTRUCTIONS = (
    VARIANT_HARMONIZATION_INSTRUCTIONS
    + '\n\n'
    + FLAG_RULES
    + """
FLAGS for this task. Kinds:
- conflict: the paper's own notations do not describe one change -- its c.
  and p. disagree, its coordinates or rsID resolve to a different allele than
  its HGVS, or its transcript names one thing and the registry another. Say
  which you kept and why. This task owns that decision; upstream only
  records both forms.
- unresolved: no genomic allele could be derived, or only part of the
  identity resolved.
- mismatch: the registry's consequence differs from the paper's where the
  paper's is the functional one (a splice-driven deletion the registry calls
  synonymous).
Not: a transcript chosen by the canonical rule or taken from the matching
registry record when the paper named none, a version number that differs
from the paper's, a nucleotide position the numbering check of State 0 found
counted from an mRNA start (its c. and p. describe one change; say the
mapping in basis), a splice variant with no protein change, a protein-only
input resolved through a registry, or which registry you used. "about" is
the variant as the paper wrote it, or null. The output is the block above
with a "flags" list beside it.
"""
)

agent = Agent(
    name='variant_harmonizer',
    instructions=BASE_SYSTEM_INSTRUCTIONS,
    model=extraction_model(),
    model_settings=extraction_model_settings(),
    output_type=model_facing_output(FlaggedReasoningBlock[HarmonizedVariant]),
    tools=[
        select_canonical_transcript,
        resolve_transcript_version,
        genomic_accession_for_gene_and_transcript,
        allele_registry_resolver,
        gnomad_style_ids_from_variant_validator,
        transcripts_fitting_description,
        clinvar_lookup,
        dbsnp_lookup,
    ],
)
