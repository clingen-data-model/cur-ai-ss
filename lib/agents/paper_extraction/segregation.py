"""Pass 4: segregation evidence, per family."""

from typing import Any

from pydantic import BaseModel, Field

from lib.agents.paper_extraction._shared import READING_THE_PAPER, _pdf_part, _run
from lib.models.segregation_analysis import SegregationEvidenceExtractionOutput


class FamilySegregation(BaseModel):
    family_id: int
    evidence: SegregationEvidenceExtractionOutput


class SegregationFindings(BaseModel):
    families: list[FamilySegregation] = Field(default_factory=list)


SEGREGATION_INSTRUCTIONS = f"""You are an expert clinical genetics curator reading one paper.

{READING_THE_PAPER}

You are given the families identified in this paper and who belongs to each. For each
family, extract its segregation evidence.

- extracted_lod_score: an explicit LOD score for that family, from text, tables or figure
  legends. Null with reasoning where the paper reports none -- most papers do not report one.
- has_unexplainable_non_segregations: true where an affected member of the family does not
  carry the variant. Say who, or why segregation is unclear.
- family_id is the id you were given for that family. Carry it back exactly, and never use
  one that was not in your list."""


def _extract_segregation_sync(
    paper_id: int,
    pdf_bytes: bytes,
    families: list[tuple[int, str]],
) -> SegregationFindings | None:
    listing = '\n'.join(f'family_id {fid}: {name}' for fid, name in families)
    prompt = f'Families:\n{listing}\n\nExtract segregation evidence for each.'
    return _run(
        'segregation',
        paper_id,
        SegregationFindings,
        SEGREGATION_INSTRUCTIONS,
        [_pdf_part(paper_id, pdf_bytes), {'type': 'text', 'text': prompt}],
    )
