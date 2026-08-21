"""Pass 3: which patient carries which variant, and which pairs are in trans."""

from typing import Any

from pydantic import BaseModel, Field

from lib.agents.paper_extraction._shared import READING_THE_PAPER, _pdf_part, _run
from lib.models.paper import PedigreeExtractionOutput
from lib.models.patient_variant_occurrences import (
    CompoundHetPair,
    PatientVariantOccurrence,
)


class CompoundHetForPatient(BaseModel):
    """CompoundHetPair carries no patient; the per-patient task did not need one."""

    patient_index: int
    pairs: list[CompoundHetPair]


class Genotypes(BaseModel):
    """Indices refer to the lists passed in, not database ids."""

    occurrences: list[PatientVariantOccurrence] = Field(default_factory=list)
    compound_het: list[CompoundHetForPatient] = Field(default_factory=list)


GENOTYPE_INSTRUCTIONS = f"""You are an expert clinical genetics curator reading one paper.

{READING_THE_PAPER}

You are given the individuals and variants already identified in this paper. Record which
individual carries which variant.

- Link only where the paper unambiguously reports the individual carries the variant, from
  text, tables or pedigree. Never link from biological plausibility, and never link a
  negative genotype (wild-type, non-carrier).
- zygosity: Homozygous (both copies), Hemizygous (single copy, typically X-linked in males),
  Heterozygous (one copy), Unknown.
- inheritance: Dominant, Recessive, Semi-dominant, X-linked, Somatic Mosaicism,
  Mitochondrial, Unknown, as the paper describes it.
- de_novo and testing_methods (at most two) as reported.
- Give a link-level disease_name only where that individual's disease differs from or
  refines the paper-level one.

COMPOUND HETEROZYGOSITY
- Pair two of an individual's heterozygous variants only where there is evidence they are in
  trans. Confirmed: the paper says compound heterozygous, or each variant is shown inherited
  from a different parent. Assumed: segregation strongly implies trans, such as a de novo
  variant alongside an inherited one. Uncertain: co-occurrence with phase not established.
- Two heterozygous variants alone are not a pair. If phase is unknown and the paper does not
  say which variants pair, return none.

INDICES
- patient_id is the position of the individual in the list you were given, counting from
  zero. variant_id is the position of the variant in the variant list you were given. These
  are positions, not database identifiers."""


def _extract_genotypes_sync(
    paper_id: int,
    pdf_bytes: bytes,
    identifiers: list[str],
    variants: list[str],
    pedigree: PedigreeExtractionOutput,
) -> Genotypes | None:
    people = '\n'.join(f'{i}. {name}' for i, name in enumerate(identifiers))
    variant_list = '\n'.join(f'{i}. {v}' for i, v in enumerate(variants))
    prompt = (
        f'Individuals (by index):\n{people}\n\n'
        f'Variants (by index):\n{variant_list}\n\n'
        'Record which individual carries which variant.'
    )
    if pedigree.found and pedigree.description:
        prompt += f'\n\nThe pedigree figure shows:\n{pedigree.description}'
    return _run(
        'genotypes',
        paper_id,
        Genotypes,
        GENOTYPE_INSTRUCTIONS,
        [_pdf_part(paper_id, pdf_bytes), {'type': 'text', 'text': prompt}],
    )
