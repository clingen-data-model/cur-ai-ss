from typing import Dict, List, Optional

import requests


class ClinVarClient:
    BASE = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'

    def __init__(self, email: str, api_key: Optional[str] = None):
        self.email = email
        self.api_key = api_key

    def _params(self, extra: Dict) -> Dict:
        params = {
            'email': self.email,
            'retmode': 'json',
            **extra,
        }
        if self.api_key:
            params['api_key'] = self.api_key
        return params

    def search(self, query: str, retmax: int = 20) -> List[str]:
        """
        Search ClinVar and return list of UIDs.

        Example query:
            "BRCA1[gene] AND pathogenic[clinical significance]"
            "NC_000017.11:g.43045700A>G"
        """
        url = f'{self.BASE}/esearch.fcgi'
        params = self._params(
            {
                'db': 'clinvar',
                'term': query,
                'retmax': retmax,
            }
        )

        r = requests.get(url, params=params)
        r.raise_for_status()
        data = r.json()

        return data.get('esearchresult', {}).get('idlist', [])

    def summary(self, ids: List[str]) -> Dict:
        """
        Fetch summary metadata for ClinVar IDs.
        """
        if not ids:
            return {}

        url = f'{self.BASE}/esummary.fcgi'
        params = self._params(
            {
                'db': 'clinvar',
                'id': ','.join(ids),
            }
        )

        r = requests.get(url, params=params)
        r.raise_for_status()
        return r.json()

    def search_and_summarize(self, query: str, retmax: int = 20) -> Dict:
        ids = self.search(query, retmax=retmax)
        return self.summary(ids)
