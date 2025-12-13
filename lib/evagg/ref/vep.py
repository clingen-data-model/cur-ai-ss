import logging


from lib.evagg.utils import RequestsWebContentClient
import requests
from typing import Dict, Sequence, Any
import typing

logger = logging.getLogger(__name__)


class VepClient:
    _web_client: RequestsWebContentClient
    _CONSEQUENCES_URL = 'https://rest.ensembl.org/vep/human/hgvs/'
    _RECODER_URL = 'https://rest.ensembl.org/variant_recoder/human/'

    def __init__(self, web_client: RequestsWebContentClient) -> None:
        self._web_client = web_client

    def fetch_consequences_with_pruning(self, transcript: str, hgvs_suffix: str) -> Any:
        # Generate possible transcript variants by pruning version suffixes
        # e.g., NM_006640.4 -> [NM_006640.4, NM_006640]
        def transcript_versions(transcript: str) -> list[str]:
            if '.' in transcript:
                base, version = transcript.rsplit('.', 1)
                # full version then base without version
                return [transcript, base]
            return [transcript]

        for t in transcript_versions(transcript):
            try:
                url = self._CONSEQUENCES_URL + f'{t}:{hgvs_suffix}'
                return self._web_client.get(
                    url,
                    params={
                        'AlphaMissense': '1',
                        'dbNSFP': 'ALL',
                        'REVEL': '1',
                        'vcf_string': '1',
                    },
                    content_type='json',
                    headers={'Content-Type': 'application/json'},
                )
            except requests.HTTPError as e:
                last_error = e

        raise last_error

    @typing.no_type_check
    def parse_recoder(
        self, recoder_response: Sequence[Dict[str, str]], hgvs_suffix: str
    ):
        record = recoder_response[0]
        alt = hgvs_suffix.split('>')[-1]
        if alt in record:
            if 'id' in record[alt]:
                return {'rsid': record[alt]['id'][0]}
        return {}

    @typing.no_type_check
    def parse_consequences(
        self,
        consequences_response: Sequence[Dict[str, str]],
    ) -> Dict[str, Any]:
        record = consequences_response[0]

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

        # 5. Any polyphen_prediction (unique)
        polyphens = {
            tx['polyphen_prediction']
            for tx in record.get('transcript_consequences', [])
            if 'polyphen_prediction' in tx
        }

        return {
            'vep.most_severe_consequence': most_severe,
            'vep.alphamissense_pred': alphamissense_pred,
            'vep.vcf_string': vcf_string,
            'vep.polyphen_predictions': list(polyphens),
        }

    def enrich(
        self,
        extracted_observation: Dict[str, str | None],
    ) -> None:
        transcript = extracted_observation.get('transcript', None)
        if not transcript:
            return
        # Determine which HGVS field to use
        if transcript.startswith('NM_'):
            hgvs_suffix = extracted_observation.get('hgvs_c')
        elif transcript.startswith('NP_'):
            hgvs_suffix = extracted_observation.get('hgvs_p')
        else:
            return

        if hgvs_suffix:
            try:
                consequences_response = self.fetch_consequences_with_pruning(
                    transcript, hgvs_suffix
                )
                extracted_observation.update(
                    self.parse_consequences(consequences_response)
                )
                recoder_response = self._web_client.get(
                    self._RECODER_URL
                    + f'{extracted_observation["transcript"]}:{hgvs_suffix}',
                    content_type='json',
                    headers={'Content-Type': 'application/json'},
                )
                extracted_observation.update(
                    self.parse_recoder(recoder_response, hgvs_suffix)
                )
            except Exception:
                logger.exception('Error occurred during VEP parsing')
