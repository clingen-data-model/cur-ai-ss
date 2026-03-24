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
    ExtractedPhenotypeResp,
    ExtractedPhenotypeUpdateRequest,
    HpoCandidate,
    HpoPhenotypeLink,
    HpoPhenotypeLinkingOutput,
    PhenotypeInfoExtractionOutput,
    PhenotypeLinkingEntry,
    PhenotypeLinkingOutput,
)
from lib.models.variant import ExtractedVariantDB, ExtractedVariantResp
