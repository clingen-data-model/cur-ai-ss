from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from lib.models.base import Base, PatchModel
from lib.models.evidence_block import EvidenceBlock
from lib.models.paper import (
    GeneDB,
    GeneResp,
    HighlightRequest,
    PaperDB,
    PaperExtractionOutput,
    PaperResp,
    PaperType,
    PaperUpdateRequest,
    PedigreeDB,
    PedigreeResp,
    PipelineStatus,
)
from lib.models.patient import (
    PatientDB,
    PatientResp,
    PatientUpdateRequest,
)
from lib.models.phenotype import (
    ExtractedPhenotype,
    ExtractedPhenotypeDB,
    ExtractedPhenotypeOutput,
    ExtractedPhenotypeResp,
    ExtractedPhenotypeUpdateRequest,
    HpoCandidate,
    HpoDB,
    HpoLinkingEntry,
    HpoLinkingOutput,
    HPOTerm,
)
from lib.models.variant import (
    EnrichedVariant,
    EnrichedVariantDB,
    EnrichedVariantResp,
    ExtractedVariantDB,
    ExtractedVariantResp,
    HarmonizedVariant,
    HarmonizedVariantDB,
    HarmonizedVariantResp,
    SpliceAI,
    VariantEnrichmentOutput,
    VariantHarmonizationOutput,
)
