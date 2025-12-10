import logging


from lib.evagg.utils import RequestsWebContentClient
from typing import Dict, Sequence, Any
import typing

logger = logging.getLogger(__name__)


class VepClient:
    _web_client: RequestsWebContentClient
    _URL = 'https://rest.ensembl.org/vep/human/hgvs/'

    def __init__(self, web_client: RequestsWebContentClient) -> None:
        self._web_client = web_client

    @typing.no_type_check
    def parse(
        self,
        res: Sequence[Dict[str, str]],
    ) -> Dict[str, Any]:
        record = res[0]

        # 1. Most severe consequence
        most_severe = record.get('most_severe_consequence')

        # 2. alphamissense_pred associated with the transcript(s) matching the most severe consequence
        alphamissense_preds = []
        for tx in record.get('transcript_consequences', []):
            if most_severe in tx.get('consequence_terms', []):
                if 'alphamissense_pred' in tx:
                    alphamissense_preds.append(tx['alphamissense_pred'])

        # Pick the first, or keep list if you want
        alphamissense_pred = alphamissense_preds[0] if alphamissense_preds else None

        # 3. vcf_string
        vcf_string = record.get('vcf_string')

        # 4. Maximum cadd_phred
        cadd_values = [
            tx['cadd_phred']
            for tx in record.get('transcript_consequences', [])
            if 'cadd_phred' in tx
        ]
        max_cadd_phred = max(cadd_values) if cadd_values else None

        # 5. Any polyphen_prediction (unique)
        polyphens = {
            tx['polyphen_prediction']
            for tx in record.get('transcript_consequences', [])
            if 'polyphen_prediction' in tx
        }

        return {
            'most_severe_consequence': most_severe,
            'alphamissense_pred': alphamissense_pred,
            'vcf_string': vcf_string,
            'cadd_phred': max_cadd_phred,
            'polyphen_predictions': list(polyphens),
        }

    def enrich(
        self,
        extracted_observations: Sequence[Dict[str, str]],
    ) -> Sequence[Dict[str, str]]:
        enriched_observations = []
        for extracted_observation in extracted_observations:
            transcript = extracted_observation.get('transcript', None)
            if not transcript:
                enriched_observations.append(extracted_observation)
                continue

            # Determine which HGVS field to use
            if transcript.startswith('NM_'):
                hgvs_suffix = extracted_observation.get('hgvs_c')
            elif transcript.startswith('NP_'):
                hgvs_suffix = extracted_observation.get('hgvs_p')
            else:
                hgvs_suffix = None

            if hgvs_suffix:
                try:
                    response = self._web_client.get(
                        self._URL
                        + f'{extracted_observation["transcript"]}:{hgvs_suffix}',
                        params={
                            'AlphaMissense': '1',
                            'CADD': '1',
                            'dbNSFP': 'ALL',
                            'REVEL': '1',
                            'SpliceAI': '1',
                            'vcf_string': '1',
                        },
                        content_type='json',
                        headers={'Content-Type': 'application/json'},
                    )
                    enriched = extracted_observation.copy()
                    enriched.update(self.parse(response))
                    enriched_observations.append(enriched)
                except Exception:
                    enriched_observations.append(extracted_observation)
        return enriched_observations
