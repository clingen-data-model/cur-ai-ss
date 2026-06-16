from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from lib.models.phenotype import HPOTerm


class MondoSynonymScope(StrEnum):
    """MONDO synonym scope from the synonym predicate."""

    EXACT = 'exact'
    RELATED = 'related'
    BROAD = 'broad'
    NARROW = 'narrow'
    UNKNOWN = 'unknown'


class MondoDiseaseScope(StrEnum):
    """Disease text scope for MONDO linking tasks."""

    PAPER = 'paper'
    OCCURRENCE = 'occurrence'


class MondoSynonym(BaseModel):
    """A structured MONDO synonym."""

    text: str
    scope: MondoSynonymScope = MondoSynonymScope.UNKNOWN
    synonym_type: str | None = None
    xrefs: list[str] = Field(default_factory=list)


class MondoTerm(BaseModel):
    """A selected MONDO ontology term."""

    mondo_id: str
    label: str


class MondoComponentMapping(BaseModel):
    """Mapping decision for one decomposed disease-text component."""

    text: str
    normalized_text: str | None = None
    role: Literal['primary', 'component', 'modifier']
    category: Literal['disease', 'phenotype', 'mixed', 'unknown']
    mapping_status: Literal['mapped', 'unmapped', 'excluded']
    mapped_ontology: Literal['MONDO', 'HPO'] | None = None
    mondo: MondoTerm | None = None
    hpo: HPOTerm | None = None
    confidence: Literal['high', 'medium', 'low'] | None = None
    relationship: Literal['exact', 'broad', 'narrow', 'related', 'partial'] | None = (
        None
    )
    reasoning: str


class MondoAgentDecision(BaseModel):
    """The MONDO linker's final decision."""

    # TODO: Add validators once the fallback schema settles. Useful invariants
    # include exact/broad decisions having no components, component_only having
    # no top-level MONDO ID, primary_partial having one primary MONDO component,
    # and mapped components having exactly one ontology payload.
    match_type: Literal[
        'exact', 'broad', 'primary_partial', 'component_only', 'none'
    ] = Field(description='Top-level disease normalization outcome.')
    mondo_id: str | None = Field(
        default=None,
        description='Selected primary MONDO identifier, or null when none is selected.',
    )
    term: str | None = Field(
        default=None,
        description='Selected primary MONDO label, or null when none is selected.',
    )
    confidence: Literal['high', 'medium', 'low'] | None = None
    components: list[MondoComponentMapping] = Field(
        default_factory=list,
        description=(
            'Fallback decomposition components. Empty when the full disease text '
            'is appropriately matched by the selected MONDO term.'
        ),
    )


class MondoTermDetail(MondoTerm):
    """Detailed MONDO term payload for agent tools."""

    definition: str | None = None
    synonyms: list[MondoSynonym] = Field(default_factory=list)
    xrefs: list[str] = Field(default_factory=list)
    exact_matches: list[str] = Field(default_factory=list)
    parents: list[MondoTerm] = Field(default_factory=list)
    children: list[MondoTerm] = Field(default_factory=list)


class MondoMatchEvidence(BaseModel):
    """One label or synonym match that supports a MONDO candidate."""

    text: str
    normalized_text: str
    type: Literal['label', 'synonym']
    score: float
    synonym_scope: MondoSynonymScope | None = None
    synonym_type: str | None = None


class MondoCandidate(BaseModel):
    """A MONDO search candidate returned to the agent."""

    mondo_id: str
    label: str
    definition: str | None = None
    score: float
    matches: list[MondoMatchEvidence] = Field(default_factory=list)


class MondoDiseaseContext(BaseModel):
    """Surrounding paper context supplied to the MONDO linking agent.

    This holds non-disease framing only. The disease string to map lives in
    ``MondoLinkingTarget.disease_text``; it is deliberately not duplicated here.
    """

    paper_title: str | None = None
    paper_abstract: str | None = None
    gene_symbol: str | None = None
    inheritance_mode: str | None = None


class MondoLinkingTarget(BaseModel):
    """Disease text target for paper- or occurrence-scoped MONDO linking."""

    scope: MondoDiseaseScope
    paper_id: int
    patient_variant_occurrence_id: int | None = None
    disease_text: str | None = Field(
        default=None,
        description=(
            'The single disease string this task must map to MONDO. Scope '
            'determines its source: the paper disease for paper-scoped tasks, '
            'or the occurrence disease for occurrence-scoped tasks.'
        ),
    )
    context: MondoDiseaseContext = Field(default_factory=MondoDiseaseContext)
