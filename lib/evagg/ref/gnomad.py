import logging
from typing import Dict

from lib.evagg.utils import RequestsWebContentClient


logger = logging.getLogger(__name__)


class GnomadClient:
    _web_client: RequestsWebContentClient
    _URL = 'https://gnomad.broadinstitute.org/api/'
    _QUERY = """
        query ($variantId: String!) {
          variant(variantId: $variantId, dataset: gnomad_r4) {
            variantId
            exome { 
              af
              faf95 {
                popmax
                popmax_population
              }
            }
            genome { 
              af 
              faf95 {
                popmax
                popmax_population
              }
            }
            sortedTranscriptConsequences {
              major_consequence
            }
            in_silico_predictors {
              id
              value
              flags
            }
          }
        }
    """

    def __init__(self, web_client: RequestsWebContentClient) -> None:
        self._web_client = web_client

    def parse(self, resp: dict[str, str]) -> dict[str, str | float]:
        variant = resp.get('data', {}).get('variant', {})

        # Basic AF fields
        ex = variant.get('exome', {}) or {}
        ge = variant.get('genome', {}) or {}

        predictors = {
            p.get('id'): float(p.get('value')) if p.get('value') else None
            for p in variant.get('in_silico_predictors', [])
        }

        return {
            'gnomad.exomes_af': ex.get('af'),
            'gnomad.genomes_af': ge.get('af'),
            'gnomad.exomes_popmax_af': ex.get('faf95', {}).get('popmax'),
            'gnomad.genomes_popmax_af': ge.get('faf95', {}).get('popmax'),
            'gnomad.exomes_popmax_population': ex.get('faf95', {}).get(
                'popmax_population'
            ),
            'gnomad.genomes_popmax_population': ge.get('faf95', {}).get(
                'popmax_population'
            ),
            'gnomad.cadd': predictors.get('cadd'),
            'gnomad.spliceai': predictors.get('spliceai_ds_max'),
        }

    def enrich(
        self,
        extracted_observation: Dict[str, str],
    ) -> None:
        vcf_string = extracted_observation.get('vep.vcf_string', None)
        response = self._web_client.get(
            self._URL + vcf_string,
            data={
                'query': self._QUERY,
                'variables': {'variantId': vcf_string},
            },
            content_type='json',
            headers={'Content-Type': 'application/json'},
        )
        extracted_observation.update(self.parse(response))
