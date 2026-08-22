"""Pass 3: which patient carries which variant, and which pairs are in trans."""

from typing import Any

from pydantic import BaseModel, Field

from lib.agents.paper_extraction._shared import READING_THE_PAPER, _pdf_part, _run
from lib.models.patient_variant_occurrences import (
    CompoundHetPair,
    PatientVariantOccurrence,
)


class CompoundHetForPatient(BaseModel):
    """CompoundHetPair carries no patient; the per-patient task did not need one."""

    patient_id: int
    pairs: list[CompoundHetPair]


class Genotypes(BaseModel):
    """Ids are the database ids the structure pass created."""

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

IDENTIFIERS
- patient_id and variant_id are the ids you were given for that individual and that variant.
  Carry them back exactly. Never invent an id, and never use one that was not in your
  lists."""


def _extract_genotypes_sync(
    paper_id: int,
    pdf_bytes: bytes,
    patients: list[tuple[int, str]],
    variants: list[tuple[int, str]],
) -> Genotypes | None:
    people = '\n'.join(f'patient_id {pid}: {name}' for pid, name in patients)
    variant_list = '\n'.join(f'variant_id {vid}: {label}' for vid, label in variants)
    prompt = (
        f'Individuals:\n{people}\n\n'
        f'Variants:\n{variant_list}\n\n'
        'Record which individual carries which variant.'
    )
    return _run(
        'genotypes',
        paper_id,
        Genotypes,
        GENOTYPE_INSTRUCTIONS,
        [_pdf_part(paper_id, pdf_bytes), {'type': 'text', 'text': prompt}],
    )
