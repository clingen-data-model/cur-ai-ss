from agents import Agent

from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
from lib.agents.core_extraction_rules import CORE_EXTRACTION_SPEC
from lib.agents.model_factory import extraction_model, extraction_model_settings

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
  - citations: the blocks of the text the value rests on, each as {"anchor", "quote"}
    (see CORE EXTRACTION RULES); at least one is required unless the value is
    Unknown/None. A value read from the pedigree description cites the pedigree's
    figure anchor with an empty quote.

- sex (EvidenceBlock[enum: Male, Female, Intersex, MTF/Transwoman/Transgender Female, FTM/Transman/Transgender Male, Ambiguous/Unable to Determine, Other, Unknown]):
  - Extract sex/gender as stated in the text, a table or the pedigree. Three
    things state it, and each on its own is enough:
    - the pedigree symbol: a square is the paper stating Male and a circle
      Female, in the notation every pedigree uses; the pedigree description
      records this in its Sex column. Cite the figure anchor with an empty
      quote. A diamond, or a symbol the description reads as sex unknown,
      is Unknown;
    - a sex-specific word for the person in the text: mother, father, sister,
      brother, son, daughter, girl, boy, woman, man, and "paternal"/"maternal"
      for the parent they name ("her brother" states Male for the brother;
      "his mother" states Female for the mother);
    - a plain statement ("a 26-year-old male").
    These are the paper saying it, not you inferring it, so none of them
    leaves sex Unknown. Unknown is for a person with no symbol, no such word
    and no statement. When the text and the figure disagree, take the text
    and raise a conflict flag.

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
  - Use the pedigree description (cite its figure anchor) and explicit carrier
    statements in text as evidence.

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
  - Evidence for the Proband case: this value follows from the HARD RULE above,
    not from new text, so there is no fresh quote to give. Cite whatever block
    identifies this patient as the proband/index case elsewhere in the paper
    instead of leaving citations empty -- an evidence block with a concrete
    value and no citation is invalid regardless of why the value was determined.

- twin_type (EvidenceBlock[enum: Monozygotic, Dizygotic, Unknown] or null):
  - Monozygotic: identical twins (count as 1 segregation)
  - Dizygotic: fraternal/non-identical twins (count as 2 segregations)
  - Unknown: twin status stated but type not specified
  - null: patient is not a twin
  - Extract only when explicitly mentioned; if not a twin, return null.

Guidelines:

1. Extract only explicitly stated information. Do NOT infer. A value the paper
   implies but does not state (an age from "in her thirties", a country from
   a surname) stays Unknown or None; say the implied value in that field's
   reasoning. That is the rule working, not a flag. A pedigree symbol and a
   kinship word are not implications: the sex rule above says why, and the
   same holds for the affected status a filled symbol shows.
2. Use enum values when possible; otherwise use "Other" or "Unknown".
3. If a field is not stated for this patient, return Unknown (or None for ages/twin_type).
4. The output also carries a "flags" list (the rule is in CORE EXTRACTION
   RULES). Kinds:
   - conflict: a stated value that differs between the table, the text, a
     figure legend and the pedigree, for this patient -- a "brother" drawn
     as a circle, a "woman" the text calls the father.
   - ambiguous: an age tied to an event the paper does not name clearly
     (a diagnosis age taken from an evaluation), or given as a range.
   Not: a field the paper leaves unstated, a value rule 1 kept at Unknown,
   a unit conversion, proband status or the relationship to the proband
   (decided by patient extraction and the pedigree; follow them), or
   obligate-carrier status (the rule above decides it). "about" is this
   patient's identifier, or null.
"""

PATIENT_DEMOGRAPHICS_AGENT_INSTRUCTIONS = (
    PATIENT_DEMOGRAPHICS_INSTRUCTIONS + '\n\n' + CORE_EXTRACTION_SPEC
)


agent = Agent(
    name='patient_demographics_extractor',
    instructions=BASE_SYSTEM_INSTRUCTIONS,
    model=extraction_model(),
    model_settings=extraction_model_settings(),
    # 7 union nodes, under Anthropic's documented limit of 16, but 23 objects
    # / 69 properties once dereferenced, which its grammar compiler refuses
    # ("The compiled grammar is too large", live 2026-09-30). output_type=None
    # sends no schema; lib.agents.manual_output validates the reply instead.
    output_type=None,
)
