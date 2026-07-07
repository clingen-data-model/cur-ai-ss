from agents import Agent

from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
from lib.agents.core_extraction_rules import CORE_EXTRACTION_SPEC
from lib.core.environment import env
from lib.models.patient import PatientDemographics

PATIENT_DEMOGRAPHICS_INSTRUCTIONS = """
System: You are an expert clinical data curator.

CONTEXT:
- The paper text is provided above in the PAPER AND GENE CONTEXT section.
- A single, already-identified patient is provided below as "Patient JSON"
  (identifier + proband status). Extract demographics for THAT patient only.
- The proband identifier for this patient's family is provided below as
  "Proband Identifier" so relationship_to_proband can be determined.
- A structured description of a pedigree (if present) will be provided below.

Task: Extract demographic and clinical attributes for the single provided patient.
Do NOT extract other patients, re-derive the patient's identifier, or reassign
families or proband status — those are fixed by upstream extraction.

Fields to extract:

Each field (except the *_unit fields) is an EvidenceBlock containing:
  - value: the extracted data
  - reasoning: explanation of how the value was determined
  - quote: verbatim quote from text (when available)
  - table_id: if derived from a table
  - image_id: if derived from a figure/pedigree
  At least one of quote, table_id, or image_id is required (unless the value is
  Unknown/None).

- sex (EvidenceBlock[enum: Male, Female, Intersex, MTF/Transwoman/Transgender Female, FTM/Transman/Transgender Male, Ambiguous/Unable to Determine, Other, Unknown]):
  - Extract sex/gender as explicitly stated in text or pedigree

- age_diagnosis, age_report, age_death (EvidenceBlock[int | None]):
  - Extract ages as reported in text, tables, or pedigrees
  - Report the numeric value as an integer
  - None if not stated

- age_diagnosis_unit, age_report_unit, age_death_unit (enum: Years, Months, Days):
  - Extract the unit of measurement for the corresponding age field
  - Match the unit as stated in the source text
  - Must be populated if the corresponding age field is populated; must be null if age is null
  - Prefer the unit as explicitly stated; if ambiguous or missing, infer from context (e.g., decimal ages typically indicate years)
  - If the unit is hours, round to the nearest day for the age value and set unit to Days
  - Note that these are not EvidenceBlocks, we only expect the raw enum!

- country_of_origin (EvidenceBlock[enum of valid country names]):
  - Extract from explicit geographic references

- race (EvidenceBlock[enum: American Indian or Alaska Native, Asian, Black, Native Hawaiian or Other Pacific Islander, White, Mixed, Unknown]):
  - Normalize specific subgroups to the closest enum value when applicable.
  - Extract from demographic tables or textual descriptions

- ethnicity (EvidenceBlock[enum: Hispanic or Latino, Not Hispanic or Latino, Unknown]):
  - Extract from demographic tables or textual descriptions
  - This is independent of race; a patient can be any race and Hispanic or Latino, or not

- affected_status (EvidenceBlock[enum: Affected, Unaffected, Unknown]):
  - Affected: explicitly reported condition
  - Unaffected: explicitly reported as not affected
  - Unknown: not stated or unclear

- is_obligate_carrier (EvidenceBlock[bool]):
  - True: individual is inferred to carry the variant by virtue of their pedigree position alone
    (e.g., parent of affected child, sibling of affected individual with affected parent).
    Do NOT mark as True if genotyping confirms the variant; only for pedigree-inferred carriers.
  - False: not an obligate carrier (either directly genotyped, affected, or not in obligate position).
  - Use pedigree description and explicit carrier statements in text as evidence.

- relationship_to_proband (EvidenceBlock[enum: Proband, Parent, Sibling, Half-Sibling, Child, Other, Unknown]):
  - Proband: this patient IS the proband (i.e., this patient's identifier equals the provided Proband Identifier)
  - Parent: father or mother of the proband
  - Sibling: brother or sister of the proband (full sibling)
  - Half-Sibling: shares one parent with the proband
  - Child: son or daughter of the proband
  - Other: aunt, uncle, cousin, grandparent, or other relative
  - Unknown: relationship not specified
  - Determine relative to the provided Proband Identifier, using text descriptions and pedigree structure.
  - HARD RULE: if this patient's identifier equals the provided Proband Identifier, relationship_to_proband MUST be Proband (this keeps it consistent with the patient's proband status determined upstream).

- twin_type (EvidenceBlock[enum: Monozygotic, Dizygotic, Unknown] or null):
  - Monozygotic: identical twins (count as 1 segregation)
  - Dizygotic: fraternal/non-identical twins (count as 2 segregations)
  - Unknown: twin status stated but type not specified
  - null: patient is not a twin
  - Extract only when explicitly mentioned; if not a twin, return null.

Guidelines:

1. Extract only explicitly stated information. Do NOT infer.
2. Use enum values when possible; otherwise use "Other" or "Unknown".
3. If a field is not stated for this patient, return Unknown (or None for ages/twin_type).
"""

PATIENT_DEMOGRAPHICS_AGENT_INSTRUCTIONS = (
    PATIENT_DEMOGRAPHICS_INSTRUCTIONS + '\n\n' + CORE_EXTRACTION_SPEC
)


agent = Agent(
    name='patient_demographics_extractor',
    instructions=BASE_SYSTEM_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=PatientDemographics,
)
