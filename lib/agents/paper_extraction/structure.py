"""Pass 1: what the paper contains -- classification, families, patients, variants."""

from typing import Any

from pydantic import BaseModel, Field

from lib.agents.paper_extraction._shared import READING_THE_PAPER, _pdf_part, _run
from lib.models.paper import PaperClassification
from lib.models.patient import PatientExtractionOutput
from lib.models.variant import Variant


class PaperStructure(BaseModel):
    """Everything that identifies what the paper contains."""

    classification: PaperClassification
    patients: PatientExtractionOutput
    variants: list[Variant] = Field(default_factory=list)


STRUCTURE_INSTRUCTIONS = f"""You are an expert clinical genetics curator reading one paper.

{READING_THE_PAPER}

Identify what the paper contains: how it should be classified, whether it can be curated at
all, which individuals it reports, how they group into families, and which variants it
reports. Demographics, phenotypes and genotypes are extracted separately -- do not attempt
them here.

PAPER TYPE AND GENE-DISEASE RELATIONSHIP
- Classify the paper as at most two of: Letter, Research, Case_series, Case_study,
  Cohort_analysis, Case_control, Unknown, Other.
- Give the disease name and mode of inheritance the paper associates with this gene, from
  the abstract, introduction or case descriptions. Omit the gene-disease relation entirely
  where neither can be identified confidently.

PAPER RELEVANCE
- Judge whether the paper supports extracting patient-variant pairs, and say why.
- The requirement is case-level or family-level identifiers that let variants and
  phenotypes be tied to specific individuals: "Patient 1", "Case 3", "Proband", "Family 1",
  pedigree labels like "II-2", subject IDs, or unique table row labels.
- Not relevant: reviews without original case-level data, meta-analyses reporting only
  aggregates, methods papers, editorials, population genetics without phenotype
  correlation, papers giving only aggregate statistics or variant counts, and papers
  mentioning patients without stable identifiers.
- Judging a paper irrelevant does not excuse extracting what it does report.

PATIENTS AND FAMILIES
- Identify every individual the paper reports data about, including unaffected relatives --
  they carry the segregation evidence.
- Proband: the primary affected individual through whom a family was ascertained. If none
  is named, the individual discussed in most detail is the proband; say so in the reasoning.
- Identifiers: the paper's own label exactly as written ("P1", "II-2", "TX-02", "Case 1"),
  preserving capitalisation; otherwise a descriptive label as written ("proband", "sister").
  Never a bare number. Where someone is only described by relation, name them relative to
  the proband ("Patient 2's brother"). For a single case report use "patient", proband.
- Skip individuals with no usable identifier, and skip aggregate statistics ("5 males").
  Do not extract authors, animal models or non-clinical mentions.
- Every patient belongs to exactly one family, named by family_identifier, matching one of
  the families you return. Group by the paper's own labels, by pedigree structure, by
  relational language and by shared family history. An individual with no identified
  relatives gets their own singleton family. Never merge unrelated patients, never split one
  family in two, never leave a patient unassigned.
- Family labels: the paper's own ("Family 1", "FAM-001") exactly; otherwise number them in
  order of appearance. Record consanguinity per family.

VARIANTS
- Extract every variant the paper explicitly reports for the target gene, exactly as
  written, from text, tables, figures and supplements. Do not expand grouped variants, and
  do not infer gene-variant associations.
- Populate transcript (NM_, ENST), protein_accession (NP_, ENSP), genomic_accession
  (NC_, NG_), lrg_accession (LRG_), gene_accession (ENSG), genomic_coordinates and
  genome_build ONLY where explicitly written. Never convert between them, never assume a
  build. Coordinates are copied exactly; accepted forms look like chr7:140453136,
  7-140453136-A-T or chr3:g.150928107A>C.
- rsid must be "rs" followed by digits. caid must be "CA" followed by digits -- SCV, SUB and
  bare ClinVar Variation IDs are not CAIDs.
- HGVS: copy explicit notation exactly. Infer only where unambiguous and needing no
  transcript choice ("Val600Glu" -> p.Val600Glu); anything requiring transcript selection
  stays null.
- variant_type: one of missense, frameshift, stop gained, splice donor, splice acceptor,
  splice region, start lost, inframe deletion, frameshift deletion, inframe insertion,
  frameshift insertion, structural, synonymous, intron, 5' UTR, 3' UTR, non-coding, unknown.
- functional_evidence: true where the paper reports assays, cell studies, animal models or
  experimental validation; false for computational prediction alone.
- main_focus: true where the paper treats the variant as its own -- novel, discussed in
  abstract or results, experimentally characterised, in the primary tables. False where
  labelled previously reported or present only as background. Judge by how the paper treats
  it, not by biological importance.
- Only return a variant carrying at least one structured identifier: hgvs_c, hgvs_p, hgvs_g,
  rsid, caid, genomic_coordinates, or a structured variant string. Accessions alone do not
  identify a variant, and neither does prose like "a VUS in this gene"."""


def _extract_structure_sync(
    paper_id: int,
    pdf_bytes: bytes,
    pedigree_description: str | None = None,
    pedigree_image_id: int | None = None,
) -> PaperStructure | None:
    prompt = 'Identify what this paper contains.'
    if pedigree_description:
        prompt += (
            f'\n\nA pedigree figure in this paper (image_id {pedigree_image_id}) shows:\n'
            f'{pedigree_description}\n\n'
            'Use it: it names individuals the text may not, and gives their sex, '
            'affected status and relationships. Cite it with that image_id.'
        )
    return _run(
        'structure',
        paper_id,
        PaperStructure,
        STRUCTURE_INSTRUCTIONS,
        [_pdf_part(paper_id, pdf_bytes), {'type': 'text', 'text': prompt}],
    )
