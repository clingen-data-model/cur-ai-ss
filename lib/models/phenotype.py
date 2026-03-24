from typing import List

from pydantic import BaseModel


class PhenotypeExtractionOutput(BaseModel):
    patient_idx: int
    text: str
    negated: bool = False
    uncertain: bool = False
    family_history: bool = False
    evidence_contexts: list[str]
    onset: str | None
    location: str | None
    severity: str | None
    modifier: str | None


class PhenotypeInfoExtractionOutput(BaseModel):
    phenotypes: List[PhenotypeExtractionOutput]


class HpoPhenotypeLink(BaseModel):
    """Link between a phenotype and an HPO term."""

    patient_idx: int
    hpo_id: str | None
    hpo_name: str | None
    hpo_reasoning: str


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
    hpo_reasoning: str | None = None
    candidates: list[HpoCandidate] | None = None  # HPO candidate suggestions for agent

    @classmethod
    def from_extraction(
        cls,
        extraction: PhenotypeExtractionOutput,
        hpo_id: str | None = None,
        hpo_name: str | None = None,
        hpo_reasoning: str | None = None,
        candidates: list[HpoCandidate] | None = None,
    ) -> 'PhenotypeLinkingEntry':
        """Create a PhenotypeLinkingEntry from a PhenotypeExtractionOutput."""
        return cls(
            **extraction.model_dump(),
            hpo_id=hpo_id,
            hpo_name=hpo_name,
            hpo_reasoning=hpo_reasoning,
            candidates=candidates,
        )


class PhenotypeLinkingOutput(BaseModel):
    """Combined phenotype extraction + HPO linking output."""

    phenotypes: List[PhenotypeLinkingEntry]
