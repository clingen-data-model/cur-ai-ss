from pathlib import Path

from pydantic import BaseModel


class SectionContent(BaseModel):
    """A titled section with content."""

    title: str
    content: str


class CurationSummaryRow(BaseModel):
    """One proband/variant pair of the curation summary.

    A proband with several variants gives several rows that share its
    `patient_id`; the pptx export puts them on the proband's slide. Publication
    and testing are repeated on every row so each slide carries them.
    """

    paper_id: int
    patient_id: int
    publication_and_testing: list[SectionContent]
    proband: list[SectionContent]
    variant_info: list[SectionContent]
    clinical_presentation: list[SectionContent]
    functional_segregation: list[SectionContent]
    score: list[SectionContent]
    pedigree_image_path: str | None = None
