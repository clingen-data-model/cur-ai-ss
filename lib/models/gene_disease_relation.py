from pydantic import BaseModel, Field

from lib.models.evidence_block import EvidenceBlock
from lib.models.patient_variant_link import Inheritance


class GeneDiseaseRelation(BaseModel):
    """Gene-disease relationship with disease name and inheritance mode."""

    disease_name: EvidenceBlock[str] = Field(
        description='Name of the disease caused by variants in this gene'
    )
    disease_inheritance_mode: EvidenceBlock[Inheritance] = Field(
        description='Mode of inheritance for this gene-disease relationship'
    )
