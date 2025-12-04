import logging
from typing import Any, Dict, Sequence

from lib.evagg.ref import NcbiLookupClient
from lib.evagg.types import Paper

logger = logging.getLogger(__name__)


class SinglePaperLibrary:
    """A class for fetching a specific set of papers from pubmed."""

    def __init__(
        self,
        ncbi_lookup_client: NcbiLookupClient,
    ) -> None:
        self._ncbi_lookup_client = ncbi_lookup_client

    def get_papers(self, query: Dict[str, Any]) -> Sequence[Paper]:
        pmid = query["pmid"]
        paper = self._ncbi_lookup_client.fetch(pmid, include_fulltext=True)
        return [paper] if paper else []
