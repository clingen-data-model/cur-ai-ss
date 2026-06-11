from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


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
    """Context supplied to the MONDO linking agent."""

    paper_title: str | None = None
    paper_abstract: str | None = None
    paper_disease_name: str | None = None
    occurrence_disease_text: str | None = None
    gene_symbol: str | None = None
    inheritance_mode: str | None = None


class MondoLinkingTarget(BaseModel):
    """Disease text target for paper- or occurrence-scoped MONDO linking."""

    scope: MondoDiseaseScope
    paper_id: int
    patient_variant_occurrence_id: int | None = None
    disease_text: str | None = None
    context: MondoDiseaseContext = Field(default_factory=MondoDiseaseContext)
