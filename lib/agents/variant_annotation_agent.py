import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple, cast

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from lib.core.environment import env
from lib.core.logging import setup_logging
from lib.models.variant import AnnotatedVariant, HarmonizedVariant, SpliceAI

setup_logging()
logger = logging.getLogger(__name__)

GNOMAD_BASE = 'https://gnomad.broadinstitute.org/api'
EUTILS_BASE = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'
VEP_BASE = 'https://rest.ensembl.org'


def _get_session_with_retries() -> requests.Session:
    """Create requests session with automatic retry logic."""
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=['GET', 'POST'],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


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


def clinvar_lookup(
    rsid: Optional[str],
    caid: Optional[str],
    hgvs_g: Optional[str],
    hgvs_c: Optional[str],
) -> AnnotatedVariant:
    headers = {'content-type': 'application/json'}
    result_variant = AnnotatedVariant(rsid=rsid, caid=caid)

    if not (caid or rsid or hgvs_g or hgvs_c):
        return result_variant

    session = _get_session_with_retries()

    term_parts = []

    if rsid:
        term_parts.append(rsid)

    if caid:
        term_parts.append(caid)

    if hgvs_g:
        term_parts.append(hgvs_g)

    if hgvs_c:
        term_parts.append(hgvs_c)

    term = ' OR '.join(term_parts)

    # Step 1: ESearch
    esearch_params = cast(
        dict[str, str | int],
        {
            'db': 'clinvar',
            'term': term,
            'retmax': 100,
            'retmode': 'json',
            'sort': 'relevance',
        },
    )

    if env.NCBI_API_KEY:
        esearch_params['api_key'] = env.NCBI_API_KEY
    if env.NCBI_EMAIL:
        esearch_params['email'] = env.NCBI_EMAIL

    try:
        r = session.get(
            f'{EUTILS_BASE}/esearch.fcgi',
            params=esearch_params,
            headers=headers,
            timeout=10,
        )
        r.raise_for_status()
        ids = r.json().get('esearchresult', {}).get('idlist', [])
    except requests.exceptions.RequestException as e:
        logger.error(f'ClinVar esearch failed for {term}: {e}')
        return result_variant
    except ValueError as e:
        logger.error(f'ClinVar esearch JSON parse failed for {term}: {e}')
        return result_variant

    if not ids:
        return result_variant

    # Step 2: ESummary
    esummary_params = {
        'db': 'clinvar',
        'id': ','.join(ids),
        'retmode': 'json',
        'rettype': 'vcv',
    }

    if env.NCBI_API_KEY:
        esummary_params['api_key'] = env.NCBI_API_KEY
    if env.NCBI_EMAIL:
        esummary_params['email'] = env.NCBI_EMAIL

    try:
        r = session.get(
            f'{EUTILS_BASE}/esummary.fcgi',
            params=esummary_params,
            headers=headers,
            timeout=10,
        )
        r.raise_for_status()
        summary = r.json().get('result', {})
    except requests.exceptions.RequestException as e:
        logger.error(f'ClinVar esummary failed for {term}: {e}')
        return result_variant
    except ValueError as e:
        logger.error(f'ClinVar esummary JSON parse failed for {term}: {e}')
        return result_variant

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
    hgvs_c: str | None,
) -> AnnotatedVariant:
    """Query Ensembl VEP for a given variant identifier and extract key annotations from the most relevant transcript."""
    if hgvs_g is not None:
        ext = f'/vep/human/hgvs/{hgvs_g}?mane=1&numbers=1&SpliceAI=2&REVEL=1&AlphaMissense=1'
        variant_id = hgvs_g
    elif hgvs_c is not None:
        ext = f'/vep/human/hgvs/{hgvs_c}?mane=1&numbers=1&SpliceAI=2&REVEL=1&AlphaMissense=1'
        variant_id = hgvs_c
    elif rsid is not None:
        ext = (
            f'/vep/human/id/{rsid}?mane=1&numbers=1&SpliceAI=2&REVEL=1&AlphaMissense=1'
        )
        variant_id = rsid
    else:
        raise ValueError('Requires rsid or hgvs_g or hgvs_c')

    session = _get_session_with_retries()
    headers = {'Content-Type': 'application/json'}

    try:
        r = session.get(VEP_BASE + ext, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.RequestException as e:
        logger.error(f'VEP lookup failed for {variant_id}: {e}')
        return AnnotatedVariant(rsid=rsid)
    except ValueError as e:
        logger.error(f'VEP JSON parse failed for {variant_id}: {e}')
        return AnnotatedVariant(rsid=rsid)

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

    session = _get_session_with_retries()

    # ---------------------
    # Step 1: GraphQL POST
    # ---------------------
    try:
        r = session.post(
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
    except requests.exceptions.RequestException as e:
        logger.error(f'gnomAD lookup failed for {gnomad_style_coordinates}: {e}')
        return result_variant
    except ValueError as e:
        logger.error(f'gnomAD JSON parse failed for {gnomad_style_coordinates}: {e}')
        return result_variant

    if 'errors' in payload:
        logger.error(
            f'gnomAD GraphQL error for {gnomad_style_coordinates}: {payload["errors"]}'
        )
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


def enrich_variant(hv: HarmonizedVariant) -> AnnotatedVariant:
    annotated = AnnotatedVariant(
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

        if hv.rsid or hv.caid or hv.hgvs_g or hv.hgvs_c:
            futures.append(
                executor.submit(clinvar_lookup, hv.rsid, hv.caid, hv.hgvs_g, hv.hgvs_c)
            )

        if hv.rsid or hv.hgvs_g or hv.hgvs_c:
            futures.append(executor.submit(vep_lookup, hv.rsid, hv.hgvs_g, hv.hgvs_c))

        # Collect results as they complete
        for future in as_completed(futures):
            try:
                result = future.result()
                if isinstance(result, AnnotatedVariant):
                    results.append(result)
            except Exception as e:
                # Fail-soft: log individual tool failure
                variant_id = (
                    hv.gnomad_style_coordinates or hv.rsid or hv.hgvs_g or hv.hgvs_c
                )
                logger.error(
                    f'Enrichment tool failed for {variant_id}: {e}', exc_info=True
                )
                continue

    # Deterministic merge phase
    # (merge after all threads complete to avoid race conditions)
    for result in results:
        for field_name, field_info in result.model_fields.items():
            value = getattr(result, field_name, None)
            if value is not None:
                setattr(annotated, field_name, value)
    return annotated


def enrich_variants_batch(
    harmonized_variants: List[HarmonizedVariant],
) -> List[AnnotatedVariant]:
    results: List[AnnotatedVariant] = []

    for i, hv in enumerate(harmonized_variants, 1):
        logger.info(
            f'Enriching variant {i}/{len(harmonized_variants)}: {hv.gnomad_style_coordinates or hv.rsid}'
        )
        try:
            annotated = enrich_variant(hv)
            results.append(annotated)
        except Exception as e:
            logger.exception(f'Failed to enrich variant: {e}')

    return results
