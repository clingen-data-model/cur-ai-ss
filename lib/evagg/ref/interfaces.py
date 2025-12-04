from typing import Optional, Protocol


class IRefSeqLookupClient(Protocol):
    def transcript_accession_for_symbol(self, symbol: str) -> str | None:
        """Get 'Reference Standard' RefSeq accession ID for the given gene symbol."""
        ...  # pragma: no cover

    def protein_accession_for_symbol(self, symbol: str) -> str | None:
        """Get 'Reference Standard' RefSeq protein accession ID for the given gene symbol."""
        ...  # pragma: no cover

    def genomic_accession_for_symbol(self, symbol: str) -> str | None:
        """Get 'Reference Standard' RefSeq genomic accession ID for the given gene symbol."""
        ...  # pragma: no cover

    def accession_autocomplete(self, accession: str) -> Optional[str]:
        """Get the latest RefSeq version for a versionless accession."""
        ...  # pragma: no cover
