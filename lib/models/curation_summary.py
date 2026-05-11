from pydantic import BaseModel


class SectionContent(BaseModel):
    """A titled section with content."""

    title: str
    content: str


class CurationSummaryRow(BaseModel):
    """A single row in the curation summary table, one per paper."""

    paper_id: int
    publication_and_testing: list[SectionContent]
    proband: list[SectionContent]
    variant_info: list[SectionContent]
    clinical_presentation: list[SectionContent]
    functional_segregation: list[SectionContent]
    score: list[SectionContent]
