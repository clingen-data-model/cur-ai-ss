from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from lib.models.base import Base, PatchModel
from lib.models.evidence_block import EvidenceBlock, HumanEvidenceBlock
from lib.models.family import (
    Family,
    FamilyCreateRequest,
    FamilyDB,
    FamilyResp,
    FamilyUpdateRequest,
)
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
    ScoringMethod,
)
from lib.models.patient import (
    PatientCreateRequest,
    PatientDB,
    PatientResp,
    PatientUpdateRequest,
    RelationshipToProband,
    TwinType,
)
from lib.models.patient_variant_link import (
    Inheritance,
    PatientVariantLink,
    PatientVariantLinkDB,
    PatientVariantLinkerOutput,
    PatientVariantLinkResp,
    TestingMethod,
    Zygosity,
)
from lib.models.phenotype import (
    ExtractedPhenotype,
    HpoCandidate,
    HpoDB,
    HPOTerm,
    PhenotypeDB,
    PhenotypeResp,
    PhenotypeUpdateRequest,
)
from lib.models.segregation import (
    FamilySegregationDB,
    FamilySegregationResp,
    FamilySegregationUpdateRequest,
    SegregationSummaryResp,
)
from lib.models.variant import (
    EnrichedVariant,
    EnrichedVariantDB,
    EnrichedVariantResp,
    HarmonizedVariant,
    HarmonizedVariantDB,
    HarmonizedVariantResp,
    SpliceAI,
    Variant,
    VariantDB,
    VariantEnrichmentOutput,
    VariantResp,
)
from lib.tasks.models import TaskDB, TaskResp
