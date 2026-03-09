from enum import Enum
from typing import List

from pydantic import BaseModel


class PhenotypeExtractionOutput(BaseModel):
    patient_id: int
    text: str
    negated: bool = False
    uncertain: bool = False
    family_history: bool = False
    notes: list[str]
    onset: str | None
    location: str | None
    severity: str | None
    modifier: str | None
    section: str | None
    confidence: float


class PhenotypeInfoExtractionOutput(BaseModel):
    phenotypes: List[PhenotypeExtractionOutput]


class HpoConfidence(str, Enum):
    """Confidence level for HPO term matching."""

    high = 'high'
    moderate = 'moderate'
    low = 'low'


class HpoPhenotypeLink(BaseModel):
    """Link between a phenotype and an HPO term."""

    patient_id: int
    hpo_id: str | None
    hpo_name: str | None
    confidence: HpoConfidence | None
    match_notes: str


class HpoPhenotypeLinkingOutput(BaseModel):
    """Output from HPO phenotype linking agent."""

    links: List[HpoPhenotypeLink]


class HpoCandidate(BaseModel):
    """HPO candidate suggestion from fuzzy matching."""

    hpo_id: str
    hpo_name: str
    similarity_score: float


class PhenotypeLinkingEntry(PhenotypeExtractionOutput):
    """Combined phenotype extraction + HPO linking for one phenotype."""

    hpo_id: str | None = None
    hpo_name: str | None = None
    hpo_confidence: HpoConfidence | None = None
    hpo_match_notes: str | None = None
    candidates: list[HpoCandidate] | None = None  # HPO candidate suggestions for agent

    @classmethod
    def from_extraction(
        cls,
        extraction: PhenotypeExtractionOutput,
        hpo_id: str | None = None,
        hpo_name: str | None = None,
        hpo_confidence: HpoConfidence | None = None,
        hpo_match_notes: str | None = None,
        candidates: list[HpoCandidate] | None = None,
    ) -> 'PhenotypeLinkingEntry':
        """Create a PhenotypeLinkingEntry from a PhenotypeExtractionOutput."""
        return cls(
            **extraction.model_dump(),
            hpo_id=hpo_id,
            hpo_name=hpo_name,
            hpo_confidence=hpo_confidence,
            hpo_match_notes=hpo_match_notes,
            candidates=candidates,
        )


class PhenotypeLinkingOutput(BaseModel):
    """Combined phenotype extraction + HPO linking output."""

    phenotypes: List[PhenotypeLinkingEntry]
