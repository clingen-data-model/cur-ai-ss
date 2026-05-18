from agents import Agent
from pydantic import BaseModel

from lib.core.environment import env

PAPER_SECTION_CLASSIFIER_INSTRUCTIONS = """
You are an expert at analyzing the structure of scientific papers.

CONTEXT:
- The paper text and gene symbol are provided above in the PAPER AND GENE CONTEXT section.

Your task is to identify all top-level section headers in the paper and classify each one as
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
"""


class SectionClassification(BaseModel):
    header: str
    relevant: bool


class PaperSectionClassificationOutput(BaseModel):
    sections: list[SectionClassification]


agent = Agent(
    name='paper_section_classifier',
    instructions=PAPER_SECTION_CLASSIFIER_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=PaperSectionClassificationOutput,
)
