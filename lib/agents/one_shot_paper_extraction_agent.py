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
from lib.agents.pedigree_describer_agent import PedigreeExtractionOutput
from lib.core.environment import env
from lib.core.logging import setup_logging
from lib.misc.pdf.paths import pdf_raw_path
from lib.models.paper import FileFormat, PaperExtractionOutput
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

    metadata: PaperExtractionOutput
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
Nest what belongs to one individual or family inside it: a patient's demographics and
compound het pairs go on that patient, a family's segregation evidence on that family.

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


def _extract_sync(paper_id: int, pdf_bytes: bytes) -> OneShotPaperExtraction | None:
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
