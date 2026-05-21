from agents import Agent
from pydantic import BaseModel

from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
from lib.core.environment import env

PAPER_SECTION_CLASSIFIER_INSTRUCTIONS = """
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

## Part 2: Assess Paper Relevance

Determine whether this paper is actually suitable for extracting patient-variant pairs.

RELEVANT papers include:
- Case reports or case series describing individual patients with specific genetic variants
- Family studies with genetic data linked to phenotypes
- Clinical studies reporting patient genotypes and phenotypes
- Any paper with extractable patient-level genetic and phenotypic data

IRRELEVANT papers include:
- Review articles or literature surveys (without case data)
- Meta-analyses or systematic reviews (aggregated data, no individual patients)
- Methods papers or technical manuscripts (without patient data)
- Editorials or opinion pieces
- Population genetics studies with no disease phenotype correlation
- Papers describing general gene function without patient cases
- Papers lacking individual patient-level data

Assess the paper holistically: does it contain specific patient information (identifiers, demographics,
phenotypes, and genetic variants that can be extracted)?

Provide a brief reasoning explaining your assessment (1-2 sentences).
"""


class SectionClassification(BaseModel):
    header: str
    relevant: bool


class PaperSectionClassificationOutput(BaseModel):
    sections: list[SectionClassification]
    is_paper_relevant: bool
    relevance_reasoning: str


PAPER_SECTION_CLASSIFIER_AGENT_INSTRUCTIONS = PAPER_SECTION_CLASSIFIER_INSTRUCTIONS

agent = Agent(
    name='paper_section_classifier',
    instructions=BASE_SYSTEM_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=PaperSectionClassificationOutput,
)
