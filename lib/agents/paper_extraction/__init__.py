"""Reading a paper, split by entity rather than by field.

One call reading the whole PDF fixed what the old markdown pipeline could not --
tables printed sideways, tables continued across pages, minus signs read as the
letter I -- but asking a single response to carry every patient's demographics,
every phenotype, every variant and every occurrence spread its attention thin.
On paper 89 it tripled patient coverage while losing all four ages the old
pipeline had captured, and on paper 1 the same input gave 6, 16, 18 and 28
patients across four runs.

So the PDF stays as the input to every pass -- that is where the perception win
came from -- but each pass returns a bounded amount, and each is its own task:

    PEDIGREE_IDENTIFICATION  figures                 -> which figure, and what it shows
    PAPER_STRUCTURE          PDF + pedigree          -> classification, families,
                                                        patients, variants
    PATIENT_DETAILS          PDF + patients          -> demographics and phenotypes
    PATIENT_GENOTYPES        PDF + patients+variants -> occurrences and compound het
    SEGREGATION_EVIDENCE     PDF + families          -> segregation evidence

The last three depend on the structure pass and on nothing else, so the queue
runs them concurrently. Being separate tasks also means each is retried, rerun
and timed on its own, and -- because the entities it needs are database rows by
then -- each is handed real ids rather than positions in a list.

This is not the old pipeline reassembled. That one decomposed by field over
scrambled markdown and inherited every docling defect. This decomposes by
entity over the PDF itself.

Excluded throughout, because they need a tool or are deterministic: HPO linking,
MONDO linking, variant harmonization, variant annotation, segregation scoring.
"""

from lib.agents.paper_extraction.details import (
    PatientDetail,
    PatientDetails,
    _extract_details_sync,
)
from lib.agents.paper_extraction.genotypes import (
    CompoundHetForPatient,
    Genotypes,
    _extract_genotypes_sync,
)
from lib.agents.paper_extraction.pedigree import _identify_pedigree_sync
from lib.agents.paper_extraction.segregation import (
    FamilySegregation,
    SegregationFindings,
    _extract_segregation_sync,
)
from lib.agents.paper_extraction.structure import (
    PaperStructure,
    _extract_structure_sync,
)
from lib.models.variant import VariantDB

__all__ = [
    'CompoundHetForPatient',
    'FamilySegregation',
    'Genotypes',
    'PaperStructure',
    'PatientDetail',
    'PatientDetails',
    'SegregationFindings',
    '_extract_details_sync',
    '_extract_genotypes_sync',
    '_extract_segregation_sync',
    '_extract_structure_sync',
    '_identify_pedigree_sync',
    'variant_label',
]


def variant_label(variant: VariantDB) -> str:
    """How a variant is named to the genotypes pass.

    The pass is given ids to carry back, but a bare id names nothing it could
    find in the paper, so each comes with the most identifying form we hold.
    """
    for value in (variant.hgvs_c, variant.hgvs_p, variant.variant, variant.hgvs_g):
        if value:
            return str(value)
    return 'unnamed variant'
