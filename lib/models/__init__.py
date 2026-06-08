from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from lib.models.agent_run import AgentRunDB, AgentRunResp
from lib.models.base import Base, PatchModel
from lib.models.conversation import (
    ChatMessageRequest,
    ChatMessageResp,
    ChatRoutingResponse,
    ConversationDB,
)
from lib.models.evidence_block import EvidenceBlock, HumanEvidenceBlock
from lib.models.family import (
    Family,
    FamilyCreateRequest,
    FamilyDB,
    FamilyResp,
    FamilyUpdateRequest,
)
from lib.models.mondo import MondoLink
from lib.models.paper import (
    FileFormat,
    GeneDB,
    GeneResp,
    HighlightRequest,
    PaperDB,
    PaperExtractionOutput,
    PaperResp,
    PaperTag,
    PaperType,
    PaperUpdateRequest,
    PedigreeDB,
    PedigreeResp,
)
from lib.models.patient import (
    PatientCreateRequest,
    PatientDB,
    PatientResp,
    PatientUpdateRequest,
)
from lib.models.patient_variant_occurrences import (
    Inheritance,
    PatientVariantOccurrence,
    PatientVariantOccurrenceDB,
    PatientVariantOccurrenceOutput,
    PatientVariantOccurrenceResp,
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
from lib.models.segregation_analysis import (
    SegregationAnalysisComputedDB,
    SegregationAnalysisResp,
    SegregationEvidence,
    SegregationEvidenceDB,
    SegregationEvidenceResp,
    SegregationEvidenceUpdateRequest,
    SequencingMethodology,
)
from lib.models.variant import (
    AnnotatedVariant,
    AnnotatedVariantDB,
    AnnotatedVariantResp,
    HarmonizedVariant,
    HarmonizedVariantDB,
    HarmonizedVariantResp,
    HarmonizedVariantUpdate,
    SpliceAI,
    Variant,
    VariantAnnotationOutput,
    VariantDB,
    VariantResp,
    VariantUpdateRequest,
)
from lib.tasks.models import TaskDB, TaskResp
