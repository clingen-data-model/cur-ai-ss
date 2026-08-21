"""Pass 2: demographics and phenotypes, for the patients pass 1 identified.

This is the pass the single-call version starved. On paper 89 it returned every
pedigree individual but no ages at all, where the old pipeline had all four.
"""

from typing import Any

from pydantic import BaseModel, Field

from lib.agents.paper_extraction._shared import READING_THE_PAPER, _pdf_part, _run
from lib.models.paper import PedigreeExtractionOutput
from lib.models.patient import PatientDemographics
from lib.models.phenotype import ExtractedPhenotype


class PatientDetail(BaseModel):
    """One patient, keyed by the identifier pass 1 assigned."""

    identifier: str
    demographics: PatientDemographics
    phenotypes: list[ExtractedPhenotype] = Field(default_factory=list)


class PatientDetails(BaseModel):
    patients: list[PatientDetail]


DETAIL_INSTRUCTIONS = f"""You are an expert clinical genetics curator reading one paper.

{READING_THE_PAPER}

You are given the individuals already identified in this paper. Describe each of them.
Return one entry per individual, using exactly the identifier you were given -- do not
rename, merge or add individuals, and do not leave any out. Unaffected relatives are
included: they carry the segregation evidence.

DEMOGRAPHICS
- sex, country_of_origin, race, ethnicity, affected_status from text, tables or pedigree.
  Affected means an explicitly reported condition; Unaffected means explicitly reported as
  not affected; otherwise Unknown.
- Ages (age_diagnosis, age_report, age_death) are integers reported exactly as the paper
  prints them. Do NOT convert between years and months -- record "9 years" as 9 with unit
  Years, "30 months" as 30 with unit Months. Each unit must be populated when its age is and
  null when it is not; an age without its unit is rejected. Ages given in hours round to
  days. Ages are the single most commonly missed value in these papers, and they usually sit
  in a table: check the tables for every individual before reporting an age as absent.
- is_obligate_carrier: true only where pedigree position alone implies carriage (parent of
  an affected child), not where genotyping confirmed it.
- relationship_to_proband: Proband, Parent, Sibling, Half-Sibling (shares one parent), Child,
  Other (aunt, uncle, cousin, grandparent), Unknown -- judged against the proband of that
  individual's own family. Someone who is the proband must be Proband.
- twin_type: Monozygotic, Dizygotic or Unknown only where twinning is mentioned; null
  otherwise.

PHENOTYPES
- A phenotype is an observable trait, sign or symptom: clinical symptoms, physical findings,
  observable signs, developmental and behavioural observations, laboratory findings
  describing patient state. Not medications, procedures, or abstract genetic concepts.
- Named syndromes and disorders are not phenotypes -- skip "Marfan syndrome", "Duchenne
  muscular dystrophy". But a diagnosis naming an observable abnormality IS one and must be
  extracted as such: "diagnosed with congenital diaphragmatic hernia" -> "congenital
  diaphragmatic hernia"; "diagnosed with epilepsy" -> "seizures"; "clinical diagnosis of
  scoliosis" -> "scoliosis". Do not skip a phenotype because it is written as a diagnosis.
- One phenotype per entry. A sentence listing three findings becomes three entries sharing
  that quote, never one entry holding a list.
- negated: the paper states the individual does NOT have it ("no tremor was observed").
  uncertain: possible or suspected ("possible seizure activity"). family_history: stated of
  a relative and not of this individual ("the patient's mother had hearing loss"). onset,
  location (body site or laterality), severity and modifier where given.
- At most TWELVE phenotypes per individual. Where more exist, keep the most clinically
  informative: congenital and structural anomalies, neurologic and developmental
  abnormalities, dysmorphic features and organ dysfunction first; persistent symptoms and
  disease-related laboratory abnormalities next; common nonspecific complaints, secondary
  complications and treatment effects last. Do not invent phenotypes to reach twelve.
- Keep the most specific of overlapping findings ("global developmental delay" over
  "developmental delay") and avoid redundant entries.
- patient_id on each phenotype is the position of its individual in the list you return,
  counting from zero."""


def _extract_details_sync(
    paper_id: int,
    pdf_bytes: bytes,
    identifiers: list[str],
    pedigree: PedigreeExtractionOutput,
) -> PatientDetails | None:
    listing = '\n'.join(f'- {name}' for name in identifiers)
    prompt = f'Individuals identified in this paper:\n{listing}\n\nDescribe each.'
    if pedigree.found and pedigree.description:
        prompt += f'\n\nThe pedigree figure shows:\n{pedigree.description}'
    return _run(
        'details',
        paper_id,
        PatientDetails,
        DETAIL_INSTRUCTIONS,
        [_pdf_part(paper_id, pdf_bytes), {'type': 'text', 'text': prompt}],
    )
