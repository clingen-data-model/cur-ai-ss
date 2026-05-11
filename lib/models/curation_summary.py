from pydantic import BaseModel


class CurationSummaryRow(BaseModel):
    """A single row in the curation summary table, one per paper."""

    paper_id: int
    publication_and_testing: str
    proband: str
    variant_info: str
    clinical_presentation: str
    functional_segregation: str
    score: str
