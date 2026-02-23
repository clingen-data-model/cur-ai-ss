from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

import requests
from pydantic import BaseModel

GNOMAD_BASE = 'https://gnomad.broadinstitute.org/api'
EUTILS_BASE = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'
VEP_BASE = 'https://rest.ensembl.org'

CLINVAR_GOLD_STARS_LOOKUP = {
    'no classification for the single variant': 0,
    'no classification provided': 0,
    'no assertion criteria provided': 0,
    'no classifications from unflagged records': 0,
    'criteria provided, single submitter': 1,
    'criteria provided, conflicting classifications': 1,
    'criteria provided, multiple submitters, no conflicts': 2,
    'reviewed by expert panel': 3,
    'practice guideline': 4,
}


class SpliceAI(BaseModel):
    max_score: float = 0.0
    effect_type: Optional[str] = None
    position: Optional[int] = None

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> 'SpliceAI':
        """Convert raw SpliceAI dict into max_score, effect_type, position"""
        ds_keys = ['DS_AG', 'DS_AL', 'DS_DG', 'DS_DL']
        dp_keys = ['DP_AG', 'DP_AL', 'DP_DG', 'DP_DL']

        max_score = 0.0
        effect_type = None
        position = None

        for ds, dp in zip(ds_keys, dp_keys):
            score = raw.get(ds, 0)
            if score > max_score:
                max_score = score
                effect_type = ds
                position = raw.get(dp)

        return cls(max_score=max_score, effect_type=effect_type, position=position)


class AnnotatedVariant(BaseModel):
    gnomad_style_coordinates: Optional[str] = None
    rsid: Optional[str] = None
    caid: Optional[str] = None
    pathogenicity: Optional[str] = None
    submissions: Optional[int] = None
    stars: Optional[int] = None
    exon: Optional[str] = None
    revel: Optional[float] = None
    alphamissense_class: Optional[str] = None
    alphamissense_score: Optional[float] = None
    spliceai: Optional[SpliceAI] = None

    # --- gnomAD ---
    gnomad_top_level_af: Optional[float] = None
    gnomad_popmax_af: Optional[float] = None
    gnomad_popmax_population: Optional[str] = None


class VariantEnrichmentOutput(BaseModel):
    variants: List[AnnotatedVariant]


def clinvar_lookup(rsid: Optional[str], caid: Optional[str]) -> AnnotatedVariant:
    headers = {'content-type': 'application/json'}
    result_variant = AnnotatedVariant(rsid=rsid, caid=caid)

    if not (caid or rsid):
        return result_variant

    term = f'{caid} AND {rsid}' if (caid and rsid) else (caid or rsid)

    # Step 1: ESearch
    r = requests.get(
        f'{EUTILS_BASE}/esearch.fcgi',
        params={
            'db': 'clinvar',
            'term': term,
            'retmax': 100,
            'retmode': 'json',
            'sort': 'relevance',
        },
        headers=headers,
        timeout=10,
    )
    r.raise_for_status()
    ids = r.json().get('esearchresult', {}).get('idlist', [])
    if not ids:
        return result_variant

    # Step 2: ESummary
    r = requests.get(
        f'{EUTILS_BASE}/esummary.fcgi',
        params={
            'db': 'clinvar',
            'id': ','.join(ids),
            'retmode': 'json',
            'rettype': 'vcv',
        },
        headers=headers,
        timeout=10,
    )
    r.raise_for_status()
    summary = r.json().get('result', {})
    uids = summary.get('uids', [])
    if not uids:
        return result_variant

    record = summary.get(uids[0], {})
    germline = record.get('germline_classification', {})

    result_variant.pathogenicity = germline.get('description', '')
    result_variant.submissions = len(
        record.get('supporting_submissions', {}).get('scv', [])
    )
    review_status = germline.get('review_status', '').strip().lower()
    result_variant.stars = CLINVAR_GOLD_STARS_LOOKUP.get(review_status, 0)
    return result_variant


def vep_lookup(
    rsid: str | None,
    hgvs_g: str | None,
) -> AnnotatedVariant:
    """Query Ensembl VEP for a given variant identifier and extract key annotations from the most relevant transcript."""
    if rsid is not None:
        ext = (
            f'/vep/human/id/{rsid}?mane=1&numbers=1&SpliceAI=2&REVEL=1&AlphaMissense=1'
        )
    elif hgvs_g is not None:
        ext = f'/vep/human/hgvs/{hgvs_g}?mane=1&numbers=1&SpliceAI=2&REVEL=1&AlphaMissense=1'
    else:
        raise ValueError('Requires rsid or hgvs_g')

    headers = {'Content-Type': 'application/json'}
    r = requests.get(VEP_BASE + ext, headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json()
    result_variant = AnnotatedVariant(rsid=rsid)

    if not data:
        return result_variant

    variant = data[0]
    transcripts = variant.get('transcript_consequences', [])
    if not transcripts:
        return result_variant

    # Prioritize MANE Select transcript
    mane_transcripts = [t for t in transcripts if t.get('mane_select')]
    if mane_transcripts:
        tx = mane_transcripts[0]
    else:
        # Fallback: highest impact transcript
        IMPACT_RANK = {'HIGH': 3, 'MODERATE': 2, 'LOW': 1, 'MODIFIER': 0}
        tx = max(
            transcripts,
            key=lambda t: IMPACT_RANK.get(t.get('impact', 'MODIFIER').upper(), 0),
        )

    # Populate fields
    result_variant.exon = tx.get('exon')
    result_variant.revel = tx.get('revel')
    result_variant.alphamissense_class = tx.get('alphamissense', {}).get('am_class')
    result_variant.alphamissense_score = tx.get('alphamissense', {}).get(
        'am_pathogenicity'
    )

    # Convert SpliceAI dict to Pydantic model
    if tx.get('spliceai'):
        result_variant.spliceai = SpliceAI.from_raw(tx['spliceai'])

    return result_variant


@function_tool
def gnomad_lookup(gnomad_style_coordinates: str) -> AnnotatedVariant:
    headers = {'content-type': 'application/json'}

    result_variant = AnnotatedVariant(gnomad_style_coordinates=gnomad_style_coordinates)

    query = """
    query ($variantId: String!) {
      variant(variantId: $variantId, dataset: gnomad_r4) {
        variantId
        joint {
          ac
          an
          populations {
            id
            ac
            an
          }
        }
      }
    }
    """

    # ---------------------
    # Step 1: GraphQL POST
    # ---------------------
    r = requests.post(
        GNOMAD_BASE,
        json={
            'query': query,
            'variables': {'variantId': gnomad_style_coordinates},
        },
        headers={
            **headers,
            'User-Agent': 'Mozilla/5.0',  # required by gnomAD
        },
        timeout=10,
    )
    r.raise_for_status()

    payload = r.json()

    if 'errors' in payload:
        return result_variant

    variant = payload.get('data', {}).get('variant')
    if not variant:
        return result_variant

    joint = variant.get('joint')
    if not joint:
        return result_variant

    # ---------------------
    # Step 2: Compute top-level AF
    # ---------------------
    ac = joint.get('ac') or 0
    an = joint.get('an') or 0

    if an:
        result_variant.gnomad_top_level_af = ac / an

    # ---------------------
    # Step 3: Filter populations
    # ---------------------
    populations = joint.get('populations') or []
    valid_pops: List[Tuple[str, float]] = []

    for pop in populations:
        pop_id = pop.get('id')
        pop_ac = pop.get('ac') or 0
        pop_an = pop.get('an') or 0

        if not pop_id:
            continue
        if pop_id == 'remaining':
            continue
        if pop_id in {'XX', 'XY'}:
            continue
        if pop_id.endswith('_XX') or pop_id.endswith('_XY'):
            continue
        if pop_an < 2000:
            continue
        if pop_an == 0:
            continue

        af = pop_ac / pop_an
        valid_pops.append((pop_id, af))

    if not valid_pops:
        return result_variant

    popmax_population, popmax_af = max(valid_pops, key=lambda x: x[1])

    result_variant.gnomad_popmax_population = popmax_population
    result_variant.gnomad_popmax_af = popmax_af

    return result_variant


from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional


def enrich_variant(hv: HarmonizedVariant) -> AnnotatedVariant:
    enriched = AnnotatedVariant(
        gnomad_style_coordinates=hv.gnomad_style_coordinates,
        rsid=hv.rsid,
        caid=hv.caid,
    )

    futures = []
    results: List[AnnotatedVariant] = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        # Submit tasks conditionally
        if hv.gnomad_style_coordinates:
            futures.append(executor.submit(gnomad_lookup, hv.gnomad_style_coordinates))

        if hv.rsid or hv.caid:
            futures.append(executor.submit(clinvar_lookup, hv.rsid, hv.caid))

        if hv.rsid or hv.hgvs_g:
            futures.append(executor.submit(vep_lookup, hv.rsid, hv.hgvs_g))

        # Collect results as they complete
        for future in as_completed(futures):
            try:
                result = future.result()
                if isinstance(result, AnnotatedVariant):
                    results.append(result)
            except Exception:
                # Fail-soft: ignore individual tool failure
                continue

    # Deterministic merge phase
    # (merge after all threads complete to avoid race conditions)
    for result in results:
        enriched = enriched.model_copy(update=result.model_dump(exclude_none=True))

    return enriched
