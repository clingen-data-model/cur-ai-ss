"""Package for interacting with reference resources."""

from .hpo import PyHPOClient, WebHPOClient
from .interfaces import (
    IAnnotateEntities,
    ICompareHPO,
    IFetchHPO,
    IGeneLookupClient,
    IPaperLookupClient,
    IRefSeqLookupClient,
    ISearchHPO,
    IVariantLookupClient,
)
from .mutalyzer import MutalyzerClient
from .ncbi import NcbiLookupClient
from .refseq import RefSeqGeneLookupClient, RefSeqLookupClient

__all__ = [
    # Interfaces.
    "IAnnotateEntities",
    "IGeneLookupClient",
    "IPaperLookupClient",
    "IVariantLookupClient",
    "IRefSeqLookupClient",
    "ICompareHPO",
    "IFetchHPO",
    "ISearchHPO",
    # NCBI.
    "NcbiLookupClient",
    "RefSeqGeneLookupClient",
    "RefSeqLookupClient",
    # Mutalyzer.
    "MutalyzerClient",
    # HPO.
    "PyHPOClient",
    "WebHPOClient",
]
