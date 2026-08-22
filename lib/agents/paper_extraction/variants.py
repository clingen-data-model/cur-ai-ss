"""Which variants the paper reports.

Split from the roster because the two were competing for one response: the
variant fields alone -- accessions, HGVS, coordinates, type, evidence flags --
are the most detailed thing we ask for per row.
"""

from pydantic import BaseModel, Field

from lib.agents.paper_extraction._shared import READING_THE_PAPER, _pdf_part, _run
from lib.models.variant import Variant


class VariantExtraction(BaseModel):
    """A list needs a wrapper: structured outputs take an object at the root."""

    variants: list[Variant] = Field(default_factory=list)


VARIANT_INSTRUCTIONS = f"""You are an expert clinical genetics curator reading one paper.

{READING_THE_PAPER}

Extract the variants this paper reports. Patients, demographics and which patient carries
which variant are extracted separately -- do not attempt those here.

VARIANTS
- Extract every variant the paper explicitly reports for the target gene, exactly as
  written, from text, tables, figures and supplements. A table listing one variant per
  patient is the usual source; work through every row. Do not expand grouped variants, and
  do not infer gene-variant associations.
- Return each distinct variant once. Where several patients carry the same variant, that is
  one entry, not one per patient -- the patient-variant links are made separately.
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
- One variant per entry. Where a patient carries two variants -- compound heterozygous, or a
  table cell holding both separated by a slash -- return them as two entries, never one
  entry holding both.
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


def _extract_variants_sync(paper_id: int, pdf_bytes: bytes) -> VariantExtraction | None:
    return _run(
        'variants',
        paper_id,
        VariantExtraction,
        VARIANT_INSTRUCTIONS,
        [
            _pdf_part(paper_id, pdf_bytes),
            {'type': 'text', 'text': 'Extract every variant this paper reports.'},
        ],
    )
