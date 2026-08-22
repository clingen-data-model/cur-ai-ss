"""How the paper should be classified, and whether it can be curated at all.

Small and cheap, and split out for that reason: it used to ride along with the
patient roster and the variants in one response, and a response holding four
sections could produce this part and then stop. On paper 92 that is exactly
what happened -- the relevance reasoning named the table of twenty-three
patients that the same response then failed to enumerate.
"""

from lib.agents.paper_extraction._shared import READING_THE_PAPER, _pdf_part, _run
from lib.models.paper import PaperClassification

CLASSIFICATION_INSTRUCTIONS = f"""You are an expert clinical genetics curator reading one paper.

{READING_THE_PAPER}

Judge what kind of paper this is and whether it can be curated. Patients, variants,
demographics and genotypes are extracted separately -- do not attempt them here.

PAPER TYPE AND GENE-DISEASE RELATIONSHIP
- Classify the paper as at most two of: Letter, Research, Case_series, Case_study,
  Cohort_analysis, Case_control, Unknown, Other.
- Give the disease name and mode of inheritance the paper associates with this gene, from
  the abstract, introduction or case descriptions. Omit the gene-disease relation entirely
  where neither can be identified confidently.

PAPER RELEVANCE
- Judge whether the paper supports extracting patient-variant pairs, and say why.
- The requirement is case-level or family-level identifiers that let variants and
  phenotypes be tied to specific individuals: "Patient 1", "Case 3", "Proband", "Family 1",
  pedigree labels like "II-2", subject IDs, or unique table row labels.
- Not relevant: reviews without original case-level data, meta-analyses reporting only
  aggregates, methods papers, editorials, population genetics without phenotype
  correlation, papers giving only aggregate statistics or variant counts, and papers
  mentioning patients without stable identifiers.
- Judging a paper irrelevant does not excuse extracting what it does report."""


def _classify_paper_sync(paper_id: int, pdf_bytes: bytes) -> PaperClassification | None:
    return _run(
        'classification',
        paper_id,
        PaperClassification,
        CLASSIFICATION_INSTRUCTIONS,
        [
            _pdf_part(paper_id, pdf_bytes),
            {'type': 'text', 'text': 'Classify this paper.'},
        ],
    )
