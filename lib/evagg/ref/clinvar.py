import logging

from lib.evagg.ref.ncbi import NcbiClientBase
from typing import Dict, Sequence

logger = logging.getLogger(__name__)


import xml.etree.ElementTree as ET


class ClinvarClient(NcbiClientBase):
    def enrich(
        self,
        extracted_observations: Sequence[Dict[str, str]],
    ) -> Sequence[Dict[str, str]]:
        enriched_observations = []
        for extracted_observation in extracted_observations:
            rsid = extracted_observation.get('rsid', None)
            if not rsid:
                enriched_observations.append(extracted_observation)
                continue
            res = self._esearch(db='clinvar', term=f'{rsid}[rs]', sort='relevance')
            id_elem = res.find('.//Id')
            if id_elem is None:
                continue
            res = self._efetch(
                db='clinvar',
                id=id_elem.text,
                retmode='xml',
                rettype='vcv',
                is_variationid='1',
            )
            clin_sig = res.find('.//Classifications/GermlineClassification/Description')
            if clin_sig is not None:
                enriched = extracted_observation.copy()
                enriched.update(
                    {
                        'clinvar_clinical_significance': clin_sig.text,
                    }
                )
                enriched_observations.append(enriched)
        return enriched_observations
