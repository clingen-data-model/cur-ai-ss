"""Single-pass curation: the PDF goes in, everything tool-free comes out.

Replaces the chain of reading agents (paper metadata, patient extraction,
demographics, pedigree, variant extraction, phenotypes, occurrences, compound
het, segregation evidence) with one structured call against the PDF itself.

Two things this buys over the chain:

- The model sees the whole paper at once, so a table split across pages or
  printed sideways is read as the single table it is. The per-table agents
  could not do this: none of them saw more than one fragment.
- Entities are produced together, so demographics and phenotypes are nested
  inside the patient they belong to. Coverage cannot drift the way it does
  when a separate pass has to re-derive the patient list.

Deliberately excluded, because they need a tool or are deterministic: HPO
linking, MONDO linking, variant harmonization, variant annotation, and
segregation analysis scoring.
"""

import asyncio
import base64
import logging

from openai import OpenAI
from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

from lib.agents.core_extraction_rules import CORE_EXTRACTION_SPEC
from lib.core.environment import env
from lib.core.logging import setup_logging
from lib.misc.pdf.paths import pdf_raw_path
from lib.models.paper import (
    FileFormat,
    PaperClassification,
    PedigreeExtractionOutput,
)
from lib.models.patient import (
    FamilyEntry,
    PatientDemographics,
    PatientIdentity,
)
from lib.models.patient_variant_occurrences import (
    CompoundHetPair,
    PatientVariantOccurrence,
)
from lib.models.phenotype import ExtractedPhenotype
from lib.models.segregation_analysis import SegregationEvidenceExtractionOutput
from lib.models.variant import Variant

setup_logging()
logger = logging.getLogger(__name__)


class OneShotPatient(PatientIdentity):
    """A patient's identity, plus what the split pipeline attached to it later.

    Demographics came from a PATIENT_DEMOGRAPHICS task per patient, and compound
    het pairs from a COMPOUND_HET_EVALUATION task per patient. Nesting them here
    means a patient cannot come back identified but undescribed, and a pair
    cannot be orphaned from the patient carrying it.
    """

    demographics: PatientDemographics
    compound_het: list[CompoundHetPair] = Field(default_factory=list)


class OneShotFamily(FamilyEntry):
    """A family, plus the segregation evidence its own task used to produce."""

    segregation: SegregationEvidenceExtractionOutput | None = None


class OneShotPaperExtraction(BaseModel):
    """Everything one paper yields that needs no secondary tool call.

    IMPORTANT -- index convention. ExtractedPhenotype.patient_id,
    PatientVariantOccurrence.patient_id/variant_id and CompoundHetPair's
    variant_id_a/variant_id_b are database ids everywhere else in the codebase.
    Here they are POSITIONS in this response's own patients and variants lists,
    counting from zero, because nothing has been written to the database when
    this is produced. persist_curation resolves them to real ids.

    Anything belonging to a single patient or family is nested inside it rather
    than carrying an index of its own.
    """

    classification: PaperClassification
    families: list[OneShotFamily]
    patients: list[OneShotPatient]
    pedigree: PedigreeExtractionOutput
    variants: list[Variant]
    phenotypes: list[ExtractedPhenotype] = Field(default_factory=list)
    occurrences: list[PatientVariantOccurrence] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_family_coverage(self) -> Self:
        """Mirrors PatientExtractionOutput: every patient belongs to a family."""
        named = {entry.family.identifier.value for entry in self.families}
        missing = {
            p.family_identifier.value
            for p in self.patients
            if p.family_identifier.value not in named
        }
        if missing:
            raise ValueError(f'Patients assigned to unlisted families: {missing}')
        return self


ONE_SHOT_INSTRUCTIONS = """You are an expert clinical genetics curator. You are given one
research paper as a PDF and you extract its entire curation in a single pass.

Everything comes from the attached PDF. You have no lookup tools, so never supply a value
the paper does not print. Bibliographic metadata is resolved separately against PubMed and
is not your concern here.

READING THE PAPER
- Clinical values, especially ages, frequently appear only in tables.
- A table may be printed sideways, or continued across pages under a "Continued" heading.
  Continuation pages are part of the same table and describe the same series of patients.
- Read figures too: pedigrees carry sex, affected status and relationships that the text
  often omits. Cite the figure with image_id when you use it.
- A value you could not read is not the same as a value the paper does not report.

PAPER TYPE AND GENE-DISEASE RELATIONSHIP
- Classify the paper as at most two of: Letter, Research, Case_series, Case_study,
  Cohort_analysis, Case_control, Unknown, Other.
  - Letter: short correspondence or brief report with limited data.
  - Research: full original article with complete methods, results and discussion.
  - Case_series: several patients or families sharing a phenotype or variant, no controls.
  - Case_study: a single patient or single family, often a rare phenotype or novel variant.
  - Cohort_analysis: a defined group selected by shared criteria, reporting frequencies,
    outcomes or genotype-phenotype correlation.
  - Case_control: affected individuals compared against unaffected controls.
  - Other covers reviews, meta-analyses, guidelines, methods and resource papers.
- Give the disease name and mode of inheritance the paper associates with this gene, from
  the abstract, introduction or case descriptions. Omit the gene-disease relation entirely
  where neither can be identified confidently.

PAPER RELEVANCE
- Judge whether this paper supports extracting patient-variant pairs at all, and say why
  in a sentence or two.
- The requirement is case-level or family-level identifiers that let variants and
  phenotypes be tied to specific individuals: "Patient 1", "Case 3", "Proband",
  "Family 1", pedigree labels like "II-2", subject IDs, or unique table row labels.
  Without them, extraction cannot proceed.
- Relevant: case reports and case series with identifiable cases; family studies linking
  genetic data to phenotypes; clinical studies reporting individual genotypes and
  phenotypes; cohort studies ONLY where individual patients or families can be
  distinguished and linked to variants.
- Not relevant: reviews and literature surveys without original case-level data;
  meta-analyses reporting only aggregates; methods or technical papers without cases;
  editorials and commentaries; population genetics without phenotype correlation; papers
  describing gene function with no patients; papers giving only aggregate statistics,
  diagnostic yields or variant counts; large cohort studies with no individual-level data;
  and papers that mention patients but give no stable identifier tying variants and
  phenotypes to specific cases.
- A paper does not need full demographics for every patient to be relevant. What matters
  is that specific variants and phenotypes can be connected to identifiable individuals
  or families.
- Judging a paper irrelevant does not excuse you from extracting whatever it does report;
  fill in everything the paper supports either way.

PATIENTS AND FAMILIES
- Identify every individual human the paper reports data about, including unaffected
  relatives -- they carry the segregation evidence.
- Proband: the primary affected individual through whom a family was ascertained. If no
  proband is named, the individual discussed in most detail is the proband; say so in the
  reasoning. Non-proband: any other described individual. A paper may contain several
  unrelated probands; extract each.
- Identifiers, in order of preference: the paper's own alphanumeric label exactly as
  written ("P1", "II-2", "TX-02", "Case 1"), preserving capitalisation and punctuation;
  otherwise a descriptive label as written ("proband", "sister"). Never a bare number.
  Where someone is only described by relation, name them relative to the proband
  ("Patient 2's brother"). For a single case report use "patient" with proband status
  Proband. Skip individuals with no usable identifier, and skip aggregate statistics
  ("5 males") -- those are not individuals.
- Do not extract authors, animal models, or non-clinical mentions.
- Every patient belongs to exactly one family, named by family_identifier, and that name
  must match one of the families you return. Group by the paper's own family labels, by
  pedigree structure, by relational language, and by shared family history. An individual
  with no identified relatives gets their own singleton family. Never merge unrelated
  patients, never split one family in two, never leave a patient unassigned.
- Family labels: use the paper's ("Family 1", "FAM-001") exactly; otherwise number them
  "Family 1", "Family 2" in order of appearance.
- Record consanguinity per family: true where the paper states or the pedigree shows the
  parents are related ("first cousins", "consanguineous"), false where stated unrelated or
  not mentioned.

DEMOGRAPHICS (on each patient)
- sex, country_of_origin, race, ethnicity, affected_status: take from text, tables or
  pedigree. Affected means an explicitly reported condition; Unaffected means explicitly
  reported as not affected; otherwise Unknown.
- Ages (age_diagnosis, age_report, age_death) are integers, reported exactly as the paper
  prints them. Do NOT convert between years and months -- record "9 years" as 9 with unit
  Years, "30 months" as 30 with unit Months. Each age unit must be populated when its age
  is populated and null when it is null. If an age is given in hours, round to days.
- is_obligate_carrier: true only where pedigree position alone implies carriage (parent of
  an affected child), not where genotyping confirmed it.
- relationship_to_proband: Proband, Parent, Sibling, Half-Sibling (shares one parent),
  Child, Other (aunt, uncle, cousin, grandparent), Unknown -- judged against the proband
  of that patient's own family. A patient who is the proband must be Proband.
- twin_type: Monozygotic, Dizygotic or Unknown only when twinning is mentioned; null
  otherwise.

VARIANTS
- Extract every variant the paper explicitly reports for the target gene, exactly as
  written, from text, tables, figures, captions and supplements. Do not expand grouped
  variants, and do not infer gene-variant associations.
- Populate transcript (NM_, ENST), protein_accession (NP_, ENSP), genomic_accession
  (NC_, NG_), lrg_accession (LRG_), gene_accession (ENSG), genomic_coordinates and
  genome_build ONLY where explicitly written. Never convert between them, never assume a
  build. Coordinates are copied exactly as printed; accepted forms look like
  chr7:140453136, 7-140453136-A-T or chr3:g.150928107A>C. Where an accession is embedded
  in HGVS, keep the HGVS intact and also record the accession.
- rsid must be "rs" followed by digits. caid must be "CA" followed by digits -- SCV, SUB
  and bare ClinVar Variation IDs are not CAIDs.
- HGVS: copy explicit notation exactly. You may infer only where the description is
  unambiguous and needs no transcript choice or coordinate resolution ("Val600Glu" ->
  p.Val600Glu). Anything requiring transcript selection stays null.
- variant_type: one of missense, frameshift, stop gained, splice donor, splice acceptor,
  splice region, start lost, inframe deletion, frameshift deletion, inframe insertion,
  frameshift insertion, structural, synonymous, intron, 5' UTR, 3' UTR, non-coding,
  unknown. Null if undeterminable.
- functional_evidence: true where the paper reports assays, cell studies, animal models or
  other experimental validation; false for computational prediction alone.
- main_focus: true where the paper treats the variant as one of its own -- described as
  novel, discussed in abstract/results/conclusions, experimentally characterised, or in the
  primary tables. False where labelled previously reported, or present only as background
  or in a summary table of known variants. Judge by how the paper treats it, not by
  biological importance.
- Only return a variant carrying at least one structured identifier: hgvs_c, hgvs_p,
  hgvs_g, rsid, caid, genomic_coordinates, or a structured variant string. Accessions
  alone do not identify a variant, and neither does prose like "a VUS in this gene".

PHENOTYPES
- A phenotype is an observable trait, sign or symptom: clinical symptoms, physical
  findings, observable signs, developmental and behavioural observations, laboratory
  findings describing patient state.
- Do not extract medications, procedures, or abstract genetic concepts like carrier status.
- Named syndromes and disorders are not phenotypes -- skip "Marfan syndrome", "Duchenne
  muscular dystrophy". But a diagnosis naming an observable abnormality IS a phenotype and
  must be extracted as one: "diagnosed with congenital diaphragmatic hernia" ->
  "congenital diaphragmatic hernia"; "diagnosed with epilepsy" -> "seizures"; "clinical
  diagnosis of scoliosis" -> "scoliosis". Do not skip a phenotype because it is written as
  a diagnosis.
- One phenotype per entry. A sentence listing three findings becomes three entries sharing
  that quote, never one entry holding a list.
- negated: the paper states the patient does NOT have it ("no tremor was observed").
  uncertain: described as possible or suspected ("possible seizure activity",
  "suggestive of hearing loss"). family_history: stated of a relative and not of this
  patient ("the patient's mother had hearing loss"). onset, location (body site or
  laterality), severity and modifier where given.
- At most TWELVE phenotypes per patient. Where more exist, keep the most clinically
  informative: congenital and structural anomalies, neurologic and developmental
  abnormalities, dysmorphic features and organ dysfunction first; persistent symptoms and
  disease-related laboratory abnormalities next; common nonspecific complaints, secondary
  complications and treatment effects last. Do not invent phenotypes to reach twelve.
- Keep the most specific of overlapping findings ("global developmental delay" over
  "developmental delay") and avoid redundant entries.

PATIENT-VARIANT OCCURRENCES
- Link a patient to a variant only where the paper unambiguously reports they carry it,
  from text, tables or pedigree. Do not link from biological plausibility, and never link a
  negative genotype (wild-type, non-carrier).
- zygosity: Homozygous (both copies), Hemizygous (single copy, typically X-linked in
  males), Heterozygous (one copy), Unknown.
- inheritance: Dominant, Recessive, Semi-dominant, X-linked, Somatic Mosaicism,
  Mitochondrial, Unknown, as the paper describes it.
- de_novo and testing_methods (at most two) as reported.
- Give a link-level disease_name only where that patient's disease differs from or refines
  the paper-level one.

COMPOUND HETEROZYGOSITY (on the patient carrying it)
- Pair two of that patient's heterozygous variants only where there is evidence they are in
  trans. Confirmed: the paper says compound heterozygous, or each variant is shown
  inherited from a different parent. Assumed: segregation strongly implies trans, such as a
  de novo variant alongside an inherited one. Uncertain: co-occurrence with phase not
  established.
- Two heterozygous variants alone are not a pair. If phase is unknown and the paper does
  not say which variants pair, return none.

SEGREGATION EVIDENCE (on each family)
- extracted_lod_score: an explicit LOD score for that family from text, tables or figure
  legends; null with reasoning where the paper reports none.
- has_unexplainable_non_segregations: true where an affected family member does not carry
  the variant. Explain who, or why segregation is unclear.

STRUCTURE OF YOUR ANSWER
- Anything belonging to one individual or family is nested inside it: a patient's
  demographics and compound het pairs on that patient, a family's segregation evidence on
  that family.
- Phenotypes and occurrences are returned as flat lists. Their patient_id and variant_id
  fields hold POSITIONS in the patients and variants lists you return in this same
  response, counting from zero -- not database ids, which do not exist yet.
"""

ONE_SHOT_INSTRUCTIONS += CORE_EXTRACTION_SPEC


def _client() -> OpenAI:
    return OpenAI(api_key=env.OPENAI_API_KEY)


def _extract_sync(paper_id: int, pdf_bytes: bytes) -> OneShotPaperExtraction | None:
    completion = _client().chat.completions.parse(
        model=env.OPENAI_VLM,
        messages=[
            {'role': 'system', 'content': ONE_SHOT_INSTRUCTIONS},
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'file',
                        'file': {
                            'filename': f'paper_{paper_id}.pdf',
                            'file_data': 'data:application/pdf;base64,'
                            + base64.b64encode(pdf_bytes).decode(),
                        },
                    },
                    {
                        'type': 'text',
                        'text': 'Extract the complete curation for this paper.',
                    },
                ],
            },
        ],
        response_format=OneShotPaperExtraction,
    )
    usage = completion.usage
    if usage:
        logger.info(
            f'Curation for paper {paper_id}: {usage.prompt_tokens} prompt, '
            f'{usage.completion_tokens} completion tokens'
        )
    return completion.choices[0].message.parsed


async def extract_paper_one_shot(
    paper_id: int, supplement_format: FileFormat | None = None
) -> OneShotPaperExtraction | None:
    """Run the single-pass curation for a paper.

    The supplement, when there is one, is appended as a second attachment so the
    model sees it in the same pass.
    """
    pdf_bytes = pdf_raw_path(paper_id).read_bytes()
    logger.info(f'Curating paper {paper_id} from PDF ({len(pdf_bytes)} bytes)')
    return await asyncio.to_thread(_extract_sync, paper_id, pdf_bytes)
