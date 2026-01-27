from enum import Enum
from typing import List, Optional

from agents import Agent, ModelSettings
from pydantic import BaseModel

from lib.evagg.utils.environment import env


class Sex(str, Enum):
    male = 'male'
    female = 'female'
    unknown = 'unknown'


class RaceEthnicity(str, Enum):
    African_American = 'African/African American'
    Latino_Admixed_American = 'Latino/Admixed American'
    Ashkenazi_Jewish = 'Ashkenazi Jewish'
    East_Asian = 'East Asian'
    Finnish = 'Finnish'
    Non_Finnish_European = 'Non-Finnish European'
    South_Asian = 'South Asian'
    Middle_Eastern = 'Middle Eastern'
    Amish = 'Amish'
    Other = 'Other'
    Unknown = 'Unknown'


# --- Patient model


class PatientInfo(BaseModel):
    # Core patient fields
    identifier: str  # Required
    sex: Sex
    age_diagnosis: Optional[str]  # exact text from source
    age_report: Optional[str]
    age_death: Optional[str]
    country_of_origin: Optional[str]
    race_ethnicity: RaceEthnicity

    # Evidence for each field
    identifier_evidence: Optional[str]
    sex_evidence: Optional[str]
    age_diagnosis_evidence: Optional[str]
    age_report_evidence: Optional[str]
    age_death_evidence: Optional[str]
    country_of_origin_evidence: Optional[str]
    race_ethnicity_evidence: Optional[str]


# --- Output wrapper


class PatientInfoExtractionOutput(BaseModel):
    patients: List[PatientInfo]


# --- Instructions for agent

PATIENT_EXTRACTION_INSTRUCTIONS = """
System: You are an expert clinical data curator.

Inputs:
- Text of a paper, case report, or patient registry entry

Task: Extract patient-level demographic information for each proband described.

Fields to extract:
- identifier: Unique identifier for the patient (e.g., Patient 1, II-2)
- sex: Use enum: male, female, unknown
- Age: capture age at diagnosis, at report, and at death if available; keep as text
- country_of_origin: Text as stated
- race/ethnicity: Use enum values: African, Asian, Caucasian, Hispanic/Latino, Middle Eastern, Native American, Pacific Islander, Other, Unknown

Guidelines:
1. Extract only explicitly stated information.
2. Preserve original wording for age and country.
3. Use enum values when possible; otherwise, return unknown/Other.
4. Provide exact evidence text for each field.  If citing a figure, in addition to the raw text
also include the title and an interpretable explanation of why the text was cited.
5. Return null for any missing fields.
6. Each patient must have a identifier; if not stated, skip that patient.

Output:
- Return a JSON object with a single field: patients (array of patient objects as above)
- Do not include extra fields.
- For undetermined fields, use null.
"""

# --- Agent definition

agent = Agent(
    name='patient_info_extractor',
    instructions=PATIENT_EXTRACTION_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=PatientInfoExtractionOutput,
    model_settings=ModelSettings(max_tokens=8192),
)
