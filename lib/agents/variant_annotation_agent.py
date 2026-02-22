from typing import List, Optional

import requests
from pydantic import BaseModel

EUTILS_BASE = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'

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


class AnnotatedVariant(BaseModel):
    gnomad_style_coordinates: Optional[str] = None
    rsid: Optional[str] = None
    caid: Optional[str] = None
    pathogenicity: str | None = None
    submissions: int | None = None
    stars: int | None = None


def clinvar_lookup(
    caid: str | None,
    rsid: str | None,
) -> AnnotatedVariant:
    headers = {'content-type': 'application/json'}

    result_variant = AnnotatedVariant(
        rsid=rsid,
        caid=caid,
    )

    if not (caid or rsid):
        return result_variant

    term = f'{caid} AND {rsid}' if (caid and rsid) else (caid or rsid)

    # ---------------------
    # Step 1: ESearch
    # ---------------------
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

    # ---------------------
    # Step 2: ESummary
    # ---------------------
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


class VariantEnrichmentOutput(BaseModel):
    variants: List[AnnotatedVariant]
