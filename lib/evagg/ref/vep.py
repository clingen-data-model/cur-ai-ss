import logging


from lib.evagg.utils import RequestsWebContentClient
from typing import Dict, Sequence

logger = logging.getLogger(__name__)


class VepClient:
    _web_client: RequestsWebContentClient

    def __init__(self, web_client: RequestsWebContentClient) -> None:
        self._web_client = web_client

    def enrich(
        extracted_fields: Sequence[Dict[str, str]],
    ) -> Sequence[Dict[str, str]]:
        return extracted_fields
