from agents import Agent
from pydantic import BaseModel

from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
from lib.core.environment import env
from lib.models.evidence_block import ReasoningBlock

PAPER_CLASSIFIER_INSTRUCTIONS = """
You are an expert at analyzing the structure and content of scientific papers.

CONTEXT:
- The paper text and gene symbol are provided above in the PAPER AND GENE CONTEXT section.

Your task has two components:

## Part 1: Classify Section Relevance

Identify all top-level section headers in the paper and classify each one as
either relevant or irrelevant for downstream clinical data extraction (patient demographics,
genetic variants, phenotypes, etc.).

Mark a section as IRRELEVANT (relevant=false) if it is purely administrative or bibliographic,
including but not limited to:
- References / Bibliography / Works Cited / Supplementary References
- Acknowledgements / Acknowledgments
- Author Contributions / Author Information
- Conflict of Interest / Competing Interests / Disclosures
- Funding / Financial Support / Grants
- Data Availability / Code Availability
- Ethics Statement / Institutional Review

Mark everything else as RELEVANT (relevant=true), including:
- Introduction / Background
- Methods / Materials and Methods / Patients and Methods
- Results / Findings / Clinical Features / Case Report / Case Description
- Discussion / Conclusion / Summary
- Supplementary Methods / Supplementary Results (content sections)
- Any other section containing clinical, variant, or phenotype information

Return a complete list of ALL section headers you find. Do not skip any sections.

Part 2: Assess Paper Relevance

Determine whether this paper is suitable for extracting patient-variant pairs.

CRITICAL REQUIREMENT:
The paper MUST contain case-level or family-level identifiers that allow genetic variants and phenotypes
to be linked to specific individuals or families. Without identifiable cases, extraction cannot proceed.

Case-level identifiers include any stable labels that distinguish patients or families within the paper, such as:
- "Patient 1", "Case 3", "Subject A"
- "Proband"
- Family IDs (e.g. "Family 1", "Kindred B")
- Pedigree identifiers (e.g. "II-2", "III:1")
- Initials, subject IDs, or unique table row labels

These identifiers may appear in:
- Main text
- Tables
- Figures
- Pedigrees
- Supplementary materials included in the provided content

RELEVANT papers include:
- Case reports or case series describing individual patients with specific genetic variants AND identifiable cases
- Family studies with genetic data linked to phenotypes AND identifiable patients/families
- Clinical studies reporting patient genotypes and phenotypes WITH individual-level case data
- Cohort studies ONLY IF individual patients/families can be distinguished and linked to variants/phenotypes
- Any paper with extractable patient-level or family-level genetic and phenotypic data tied to identifiable cases

IRRELEVANT papers include:
- Review articles or literature surveys without original case-level data
- Meta-analyses or systematic reviews with only aggregated data
- Methods papers or technical manuscripts without patient cases
- Editorials, commentaries, or opinion pieces
- Population genetics studies without disease phenotype correlation or identifiable cases
- Papers describing general gene function without patient cases
- Papers containing only aggregate statistics, diagnostic yields, variant counts, or gene-level summaries
- Large diagnostic or observational cohort studies that do NOT provide individual-level extractable case data
- Papers mentioning patients but providing no stable identifiers linking variants and phenotypes to specific cases

IMPORTANT:
A paper does NOT need detailed demographics for every patient to be RELEVANT. The key requirement is that
specific variants and phenotypes can be linked to identifiable individuals or families.

Assess the paper holistically:
Can specific variants, phenotypes, and case identifiers be connected in a way that supports structured extraction
of patient-variant relationships?

Also provide a brief reasoning (1-2 sentences) explaining your assessment.
"""


class SectionClassification(BaseModel):
    header: str
    relevant: bool


class PaperSectionClassificationOutput(BaseModel):
    sections: list[SectionClassification]
    is_paper_relevant: ReasoningBlock[bool]


PAPER_CLASSIFIER_AGENT_INSTRUCTIONS = PAPER_CLASSIFIER_INSTRUCTIONS

agent = Agent(
    name='paper_classifier',
    instructions=BASE_SYSTEM_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=PaperSectionClassificationOutput,
)
