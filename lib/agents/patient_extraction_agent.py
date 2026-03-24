from agents import Agent

from lib.agents.core_extraction_rules import CORE_EXTRACTION_SPEC
from lib.core.environment import env
from lib.models.patient import Patient, PatientExtractionOutput

PATIENT_EXTRACTION_INSTRUCTIONS = f"""
System: You are an expert clinical data curator.

Inputs:
- Text of a paper, case report, or patient registry entry
- A structured description of a pedigree included in the paper.
   The description will include:
      - image_id (integer index of the pedigree image out of all images in the paper)
      - description

   The description summarizes pedigree structure including relationships, affected status, and any genotype or segregation information visible in the figure.

   If the description is null, there was no pedigree image included in the paper.

Task: Extract patient-level demographic information for each individual human patient explicitly described in the text, distinguishing clearly between probands and non-probands.

Definitions:
- Proband: The primary affected individual(s) through whom a family was ascertained for the study.
- Non-proband: Any other explicitly described human individual (e.g., sibling, parent, affected relative, unrelated patient in a cohort).

Notes:
- Some papers may contain multiple unrelated probands; extract each separately.
- Extract only individuals with explicitly stated demographic or clinical information.

Fields to extract (for each patient):

Each field is an EvidenceBlock containing:
  - value: the extracted data
  - reasoning: explanation of how the value was determined
  - quote: verbatim quote from text (when available)
  - table_id: if derived from a table
  - image_id: if derived from a figure/pedigree
  At least one of quote, table_id, or image_id is required.

- identifier (EvidenceBlock[string]):
  - A clear textual identifier (e.g., Patient 1, II-2, proband, index case, sibling, mother).
  - Do NOT return numeric-only identifiers.
  - If an individual has no usable textual identifier, skip that patient.

  Identifier priority rules:
    1. Prefer explicit alphanumeric identifiers exactly as written (e.g., "P1", "II-2", "Case 1").
       - Preserve capitalization and punctuation.
       - Do NOT normalize or reinterpret.
    2. If none exists, use descriptive labels (e.g., "proband", "sister") as written.
    3. Preserve exact wording when multiple probands or cases are distinguished.

- proband_status (EvidenceBlock[enum: Proband, Non-Proband, Unknown]):
  - Proband: explicitly described as proband/index case
  - Non-Proband: clearly another cohort member or relative
  - Unknown: unclear

- sex (EvidenceBlock[enum: Male, Female, Intersex, MTF/Transwoman/Transgender Female, FTM/Transman/Transgender Male, Ambiguous/Unable to Determine, Other, Unknown]):
  - Extract sex/gender as explicitly stated in text or pedigree

- age_diagnosis, age_report, age_death (EvidenceBlock[int | None]):
  - Extract ages as reported in text, tables, or pedigrees
  - None if not stated

- country_of_origin (EvidenceBlock[enum of valid country names]):
  - Extract from explicit geographic references

- race_ethnicity (EvidenceBlock[enum: African/African American, Latino/Admixed American, Ashkenazi Jewish, East Asian, Finnish, Non-Finnish European, South Asian, Middle Eastern, Amish, Other, Unknown]):
  - Normalize specific subgroups to the closest enum value when applicable.
  - Extract from demographic tables or textual descriptions

- affected_status (EvidenceBlock[enum: Affected, Unaffected, Unknown]):
  - Affected: explicitly reported condition
  - Unaffected: explicitly reported as not affected
  - Unknown: not stated or unclear

Guidelines:

1. Extract only explicitly stated information. Do NOT infer.
2. Distinguish probands from non-probands.
3. Extract only individuals with identifiable patient-level information.
4. If only aggregate statistics are provided (e.g., "5 males"), do not extract individuals.
5. Each patient must have an identifier; otherwise skip.
6. If no identifiable human patients are present, return "unknown".
7. For relational descriptions (e.g., "proband's sister"), simplify identifier to the role (e.g., "sister").
8. For single case reports:
   - Use identifier: "patient"
   - Set proband_status to "Proband"
9. Do not extract authors, non-clinical mentions, or animal models.
10. Use enum values when possible; otherwise use "Other" or "Unknown".
11. Missing fields should be returned as null (not omitted from the structured output).
"""

agent = Agent(
    name='patient_info_extractor',
    instructions=(PATIENT_EXTRACTION_INSTRUCTIONS + '\n\n' + CORE_EXTRACTION_SPEC),
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=PatientExtractionOutput,
)
