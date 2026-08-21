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
from pydantic import BaseModel, Field

from lib.agents.core_extraction_rules import CORE_EXTRACTION_SPEC
from lib.core.environment import env
from lib.core.logging import setup_logging
from lib.misc.pdf.paths import pdf_raw_path
from lib.models.evidence_block import EvidenceBlock, ReasoningBlock
from lib.models.paper import FileFormat, PaperExtractionOutput
from lib.models.patient import (
    Family,
    PatientDemographics,
    ProbandStatus,
)
from lib.models.patient_variant_occurrences import (
    CompoundHetConfidence,
    Inheritance,
    TestingMethod,
    Zygosity,
)
from lib.models.segregation_analysis import SegregationEvidenceExtractionOutput
from lib.models.variant import Variant

setup_logging()
logger = logging.getLogger(__name__)


class CuratedPhenotype(BaseModel):
    """A phenotype as the paper states it, before any HPO linking."""

    concept: EvidenceBlock[str]
    negated: bool = False
    uncertain: bool = False
    family_history: bool = False
    onset: str | None = None
    location: str | None = None
    severity: str | None = None
    modifier: str | None = None


class CuratedPatient(BaseModel):
    """One individual, with everything knowable about them from the paper.

    Demographics and phenotypes are nested rather than collected by separate
    passes: a patient cannot end up with an identity but no demographics.
    """

    identifier: EvidenceBlock[str]
    family_identifier: EvidenceBlock[str]
    proband_status: EvidenceBlock[ProbandStatus]
    demographics: PatientDemographics
    phenotypes: list[CuratedPhenotype] = Field(default_factory=list)


class CuratedFamily(BaseModel):
    family: Family
    patient_identifiers: list[EvidenceBlock[str]]


class CuratedOccurrence(BaseModel):
    """Which patient carries which variant.

    Keyed by position in this response's own ``patients`` and ``variants``
    lists. The database ids the pipeline's occurrence agent is handed do not
    exist yet when this runs.
    """

    patient_index: int
    variant_index: int
    zygosity: EvidenceBlock[Zygosity]
    inheritance: EvidenceBlock[Inheritance]
    de_novo: EvidenceBlock[bool]
    testing_methods: list[EvidenceBlock[TestingMethod]] = Field(max_length=2)


class CuratedCompoundHet(BaseModel):
    patient_index: int
    variant_index_a: int
    variant_index_b: int
    confidence: ReasoningBlock[CompoundHetConfidence]


class CuratedSegregation(BaseModel):
    """Segregation evidence for one family.

    SegregationEvidenceDB is keyed by family, so this cannot be a single
    paper-level object the way the rest of the metadata is.
    """

    family_index: int
    evidence: SegregationEvidenceExtractionOutput


class CuratedPedigree(BaseModel):
    found: bool
    description: str | None = None


class FullCuration(BaseModel):
    """Everything one paper yields that needs no secondary tool call."""

    metadata: PaperExtractionOutput
    families: list[CuratedFamily]
    patients: list[CuratedPatient]
    pedigree: CuratedPedigree
    variants: list[Variant]
    occurrences: list[CuratedOccurrence]
    compound_het: list[CuratedCompoundHet] = Field(default_factory=list)
    segregation: list[CuratedSegregation] = Field(default_factory=list)


CURATION_INSTRUCTIONS = """You are a genetics curator extracting structured data from a
research paper. Work only from the attached PDF; every value must be supported by it.

Cover every individual the paper reports data about -- probands, affected relatives, and
unaffected relatives alike. Unaffected relatives carry the segregation evidence, so
omitting them loses real data. Use the identifiers the paper itself uses ("Patient 5a",
"MMR1", "III-4", "TX-02"); where an individual is only described by relation, name them
relative to the proband ("Patient 2's brother") and assign them to that proband's family.

Read the tables carefully. A table may be printed sideways, or continued across several
pages under a "Continued" heading -- those continuation pages are part of the same table,
and the patients in them are the same series. Clinical values, especially ages, often
appear only in tables.

Report ages exactly as the paper prints them, with the unit the paper uses. Do not
convert between years and months; record 9 years as 9 with unit Years. An age and its
unit must both be present or both be null -- an age without its unit is rejected, so
never give a number without saying whether it is years or months.

occurrences and compound_het refer to patients and variants by their position in the
patients and variants lists you return in this same response, counting from zero.
segregation entries refer to families the same way, by position in the families list.

If the paper genuinely does not report something, leave it null -- but check the tables
and figures before concluding a value is absent. A value you could not read is not the
same as a value the paper does not report.

Every EvidenceBlock you return must carry at least one of quote, table_id or image_id.
Reasoning alone is rejected. Sex read off a pedigree figure needs its image_id; a value
read from a table needs that table's id.
"""

CURATION_INSTRUCTIONS += CORE_EXTRACTION_SPEC


def _client() -> OpenAI:
    return OpenAI(api_key=env.OPENAI_API_KEY)


def _curate_sync(paper_id: int, pdf_bytes: bytes) -> FullCuration | None:
    completion = _client().chat.completions.parse(
        model=env.OPENAI_VLM,
        messages=[
            {'role': 'system', 'content': CURATION_INSTRUCTIONS},
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
        response_format=FullCuration,
    )
    usage = completion.usage
    if usage:
        logger.info(
            f'Curation for paper {paper_id}: {usage.prompt_tokens} prompt, '
            f'{usage.completion_tokens} completion tokens'
        )
    return completion.choices[0].message.parsed


async def curate_paper(
    paper_id: int, supplement_format: FileFormat | None = None
) -> FullCuration | None:
    """Run the single-pass curation for a paper.

    The supplement, when there is one, is appended as a second attachment so the
    model sees it in the same pass.
    """
    pdf_bytes = pdf_raw_path(paper_id).read_bytes()
    logger.info(f'Curating paper {paper_id} from PDF ({len(pdf_bytes)} bytes)')
    return await asyncio.to_thread(_curate_sync, paper_id, pdf_bytes)
