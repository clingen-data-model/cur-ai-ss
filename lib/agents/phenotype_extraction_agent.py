from enum import Enum
from typing import List, Optional

import requests
from agents import Agent, function_tool

from lib.core.environment import env
from lib.models import PhenotypeInfoExtractionOutput


PHENOTYPE_EXTRACTION_INSTRUCTIONS = """
You are an expert clinical data curator.

Input:
- Full text of an academic paper, case report, or registry entry.

Task Overview:
- Extract all mentions of human phenotypic features (observable traits, signs, or symptoms) from the text.
- **Do NOT extract diseases, diagnoses, syndromes, laboratory results, medications, or procedures. Only extract phenotypes.**
- For each phenotype mention, return a structured JSON object that **exactly matches the following schema**:

Fields:
1. text: the exact phrase in the text describing the phenotype (string).
2. negated: true or false (boolean) if the text explicitly states the patient does NOT have the phenotype.
3. uncertain: true or false (boolean) if the text describes the phenotype as possible, suspected, or unclear.
4. family_history: true or false (boolean) if the phenotype is mentioned in the context of family history rather than the patient.
5. notes: any additional relevant context or clarification from the text (string, optional, e.g., sentence or paragraph containing the phenotype).
6. onset: optional string describing the age or disease stage when the phenotype occurred (e.g., "infancy", "adult onset").
7. location: optional string describing body site or laterality if specified (e.g., "left arm", "bilateral").
8. severity: optional string describing the severity of the phenotype if mentioned (e.g., "mild", "severe").
9. modifier: optional string capturing additional qualifiers (e.g., "intermittent", "progressive").
10. section: optional string indicating which section of the paper the phenotype was mentioned in (e.g., "case report", "results", "discussion").
11. confidence: optional float (0–1) reflecting your confidence in the extraction if available.

Instructions:
- Include every phenotype mention, even if repeated, but capture its context and flags correctly.
- Output a **list of JSON objects**, one per extracted phenotype.
- Ensure all booleans are true or false (not "yes"/"no" or strings) and all required fields are present.
- Use evidence from the text to justify negation, uncertainty, or family history flags in 'notes'.
- Populate optional fields if information is present; otherwise, leave them null or omit them.
- Do not include diseases or other non-phenotypic information.
"""

# --- Agent definition

agent = Agent(
    name='phenotype_extractor',
    instructions=PHENOTYPE_EXTRACTION_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=PhenotypeInfoExtractionOutput,
)
