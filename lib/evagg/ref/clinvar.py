import logging
from typing import Dict

from lib.evagg.ref.ncbi import NcbiClientBase

logger = logging.getLogger(__name__)


class ClinvarClient(NcbiClientBase):
    def enrich(
        self,
        extracted_observation: Dict[str, str],
    ) -> None:
        rsid = extracted_observation.get('rsid', None)
        if not rsid:
            return
        res = self._esearch(db='clinvar', term=f'{rsid}[rs]', sort='relevance')
        id_elem = res.find('.//Id')
        if id_elem is None:
            return
        res = self._efetch(
            db='clinvar',
            id=id_elem.text,
            retmode='xml',
            rettype='vcv',
            is_variationid='1',
        )
        clin_sig = res.find('.//Classifications/GermlineClassification/Description')
        if clin_sig is not None:
            extracted_observation.update(
                {
                    'clinvar.clinical_significance': clin_sig.text,
                }
            )
