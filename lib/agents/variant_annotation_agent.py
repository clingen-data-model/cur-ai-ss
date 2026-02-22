from typing import Any, Dict, List, Optional

import requests
from pydantic import BaseModel

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


# ----------------------------
# Pydantic models
# ----------------------------
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


class VariantEnrichmentOutput(BaseModel):
    variants: List[AnnotatedVariant]


# ----------------------------
# ClinVar lookup
# ----------------------------
def clinvar_lookup(caid: Optional[str], rsid: Optional[str]) -> AnnotatedVariant:
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


# ----------------------------
# VEP lookup
# ----------------------------
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
