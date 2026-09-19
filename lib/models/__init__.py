from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from lib.models.base import Base, PatchModel
from lib.models.chat_message import (
    ChatMessageCreateRequest,
    ChatMessageDB,
    ChatMessageResp,
    ChatRole,
)
from lib.models.edit import EditDB
from lib.models.evidence_block import EvidenceBlock, HumanEvidenceBlock
from lib.models.family import (
    Family,
    FamilyCreateRequest,
    FamilyDB,
    FamilyResp,
    FamilyUpdateRequest,
)
from lib.models.mondo import (
    MondoAgentDecision,
    MondoCandidate,
    MondoComponentMapping,
    MondoDiseaseScope,
    MondoLinkingTarget,
    MondoMatchEvidence,
    MondoSynonym,
    MondoSynonymScope,
    MondoTerm,
    MondoTermDetail,
)
from lib.models.paper import (
    FileFormat,
    GeneDB,
    GeneResp,
    HighlightRequest,
    PaperDB,
    PaperExtractionOutput,
    PaperResp,
    PaperReviewUpdateRequest,
    PaperSummaryResp,
    PaperTag,
    PaperType,
    PaperUpdateRequest,
    PedigreeDB,
    PedigreeResp,
    ReviewStatus,
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
    PatientVariantOccurrenceCreateRequest,
    PatientVariantOccurrenceDB,
    PatientVariantOccurrenceOutput,
    PatientVariantOccurrenceResp,
    PatientVariantOccurrenceUpdateRequest,
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
from lib.models.snapshot import PaperResetRequest, PaperResetResp, SnapshotMeta
from lib.models.user import (
    ChangePasswordRequest,
    LoginRequest,
    TokenResp,
    UserCreateRequest,
    UserDB,
    UserResp,
    UserSettingsUpdateRequest,
    UserSummaryResp,
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
    VariantCreateRequest,
    VariantDB,
    VariantResp,
    VariantUpdateRequest,
)
from lib.tasks.models import TaskDB, TaskResp
