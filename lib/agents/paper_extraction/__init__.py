"""Extraction, split by entity rather than by field.

One call reading the whole PDF fixed what the old markdown pipeline could not --
tables printed sideways, tables continued across pages, minus signs read as the
letter I -- but asking a single response to carry every patient's demographics,
every phenotype, every variant and every occurrence spread its attention thin.
On paper 89 it tripled patient coverage while losing all four ages the old
pipeline had captured, and on paper 1 the same input gave 6, 16, 18 and 28
patients across four runs.

So the PDF stays as the input to every pass -- that is where the perception win
came from -- but each pass returns a bounded amount:

    0  figures                 → which figure is the pedigree, and what it shows
    1  PDF + pedigree          → classification, families, patients, variants
    2  PDF + patients          → demographics and phenotypes per patient
    3  PDF + patients+variants → occurrences and compound het
    4  PDF + families          → segregation evidence

Passes 2, 3 and 4 all depend on pass 1 and on nothing else, so they run
together rather than in sequence.

This is not the old pipeline reassembled. That one decomposed by field over
scrambled markdown and inherited every docling defect. This decomposes by
entity over the PDF itself.

Excluded throughout, because they need a tool or are deterministic: HPO linking,
MONDO linking, variant harmonization, variant annotation, segregation scoring.
"""

import asyncio
import json
import logging

from pydantic import BaseModel

from lib.agents.paper_extraction.details import PatientDetails, _extract_details_sync
from lib.agents.paper_extraction.genotypes import Genotypes, _extract_genotypes_sync
from lib.agents.paper_extraction.pedigree import _identify_pedigree_sync
from lib.agents.paper_extraction.segregation import (
    SegregationFindings,
    _extract_segregation_sync,
)
from lib.agents.paper_extraction.structure import (
    PaperStructure,
    _extract_structure_sync,
)
from lib.misc.pdf.paths import pdf_figures_json_path, pdf_raw_path
from lib.models.paper import (
    FileFormat,
    PaperClassification,
    PedigreeExtractionOutput,
)
from lib.models.patient import PatientExtractionOutput
from lib.models.variant import Variant

logger = logging.getLogger(__name__)

__all__ = [
    'Genotypes',
    'PaperExtraction',
    'PatientDetails',
    'SegregationFindings',
    'extract_paper',
]


class PaperExtraction(BaseModel):
    """What the passes produce, assembled."""

    classification: PaperClassification
    pedigree: PedigreeExtractionOutput
    patients: PatientExtractionOutput
    details: PatientDetails
    variants: list[Variant]
    genotypes: Genotypes
    segregation: SegregationFindings


def _variant_label(variant: Variant) -> str:
    """How a variant is named back to the model in later passes."""
    for field in (variant.hgvs_c, variant.hgvs_p, variant.variant, variant.hgvs_g):
        if field and field.value:
            return str(field.value)
    return 'unnamed variant'


async def extract_paper(
    paper_id: int, supplement_format: FileFormat | None = None
) -> PaperExtraction | None:
    """Run every pass for one paper and assemble the result."""
    pdf_bytes = pdf_raw_path(paper_id).read_bytes()
    logger.info(f'Extracting paper {paper_id} from PDF ({len(pdf_bytes)} bytes)')

    figures_file = pdf_figures_json_path(paper_id)
    figures = json.loads(figures_file.read_text()) if figures_file.exists() else []
    if not figures:
        logger.info(
            f'Paper {paper_id} has no extracted figures; it may predate the current '
            'parse step and need re-parsing before a pedigree can be found'
        )

    pedigree = await asyncio.to_thread(_identify_pedigree_sync, paper_id, figures)
    pedigree = pedigree or PedigreeExtractionOutput(found=False)

    structure = await asyncio.to_thread(
        _extract_structure_sync, paper_id, pdf_bytes, pedigree
    )
    if structure is None:
        raise ValueError(f'Paper {paper_id}: structure pass returned no parsed output')

    identifiers = [p.identifier.value for p in structure.patients.patients]
    families = [e.family.identifier.value for e in structure.patients.families]
    variant_labels = [_variant_label(v) for v in structure.variants]

    # Everything below needs pass 1 and nothing else, so it goes out together.
    details, genotypes, segregation = await asyncio.gather(
        asyncio.to_thread(
            _extract_details_sync, paper_id, pdf_bytes, identifiers, pedigree
        ),
        asyncio.to_thread(
            _extract_genotypes_sync,
            paper_id,
            pdf_bytes,
            identifiers,
            variant_labels,
            pedigree,
        ),
        asyncio.to_thread(
            _extract_segregation_sync, paper_id, pdf_bytes, families, pedigree
        ),
    )

    return PaperExtraction(
        classification=structure.classification,
        pedigree=pedigree,
        patients=structure.patients,
        details=details or PatientDetails(patients=[]),
        variants=structure.variants,
        genotypes=genotypes or Genotypes(),
        segregation=segregation or SegregationFindings(),
    )
