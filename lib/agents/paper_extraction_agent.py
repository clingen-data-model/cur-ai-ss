from enum import Enum
from typing import List, Optional

from agents import Agent, ModelSettings
from pydantic import BaseModel

from lib.evagg.utils.environment import env


class PaperExtractionOutput(BaseModel):
    first_author: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    doi: str | None = None
    title: str | None = None
    abstract: str | None = None
    journal: str | None = None
    pub_year: int | None = None
    citation: str | None = None
    link: str | None = None


PAPER_EXTRACTION_INSTRUCTIONS = """
System: You are an expert clinical data curator.

Inputs:
- Text of a paper, case report, or patient registry entry

Task: Extract metadata about a provided fulltext paper.
"""

# --- Agent definition

agent = Agent(
    name='paper_extractor',
    instructions=PAPER_EXTRACTION_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=PaperExtractionOutput,
)
