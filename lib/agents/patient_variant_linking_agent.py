from enum import Enum
from typing import Generic, List, Literal, Optional, TypeVar

from agents import Agent
from lib.modles.evidence_block import EvidenceBlock
from pydantic import BaseModel, model_validator
from typing_extensions import Self

from lib.core.environment import env


# ------------------------------
# Enums
# ------------------------------
class Zygosity(str, Enum):
    homozygous = 'homozygous'
    hemizygous = 'hemizygous'
    heterozygous = 'heterozygous'
    compound_heterozygous = 'compound heterozygous'
    unknown = 'unknown'


class Inheritance(str, Enum):
    dominant = 'dominant'
    recessive = 'recessive'
    semi_dominant = 'semi-dominant'
    x_linked = 'X-linked'
    de_novo = 'de novo'
    somatic_mosaicism = 'somatic mosaicism'
    mitochondrial = 'mitochondrial'
    unknown = 'unknown'


class TestingMethod(str, Enum):
    Chromosomal_microarray = 'Chromosomal_microarray'
    Next_generation_sequencing_panels = 'Next_generation_sequencing_panels'
    Exome_sequencing = 'Exome_sequencing'
    Genome_sequencing = 'Genome_sequencing'
    Sanger_sequencing = 'Sanger_sequencing'
    Pcr = 'PCR'
    Homozygosity_mapping = 'Homozygosity_mapping'
    Linkage_analysis = 'Linkage_analysis'
    Genotyping = 'Genotyping'
    Denaturing_gradient_gel = 'Denaturing_gradient_gel'
    High_resolution_melting = 'High_resolution_melting'
    Restriction_digest = 'Restriction_digest'
    Single_strand_conformation_polymorphism = 'Single_strand_conformation_polymorphism'
    Unknown = 'Unknown'
    Other = 'Other'


# ------------------------------
# PatientVariantLink
# ------------------------------
class PatientVariantLink(BaseModel):
    patient_idx: int
    variant_id: int
    zygosity: EvidenceBlock[Zygosity]
    inheritance: EvidenceBlock[Inheritance]
    testing_methods: List[EvidenceBlock[TestingMethod]]
    confidence: Literal['high', 'moderate', 'low']

    @model_validator(mode='after')
    def max_two_methods(self) -> Self:
        if len(self.testing_methods) > 2:
            raise ValueError('testing_methods must contain at most two items')
        return self


# ------------------------------
# Output
# ------------------------------
class PatientVariantLinkerOutput(BaseModel):
    links: List[PatientVariantLink]


INSTRUCTIONS = """
You are an expert clinical genetic data curator performing structured evidence extraction 
from biomedical literature.

Your task is to LINK patients described in the paper to variants in the target gene of interest.

You are given:

1. The target gene of interest.
2. The full academic paper text.
3. A structured list of extracted variants. Each variant includes:
   - variant_id (integer index)
   - variant_evidence_context (text snippet from the paper mentioning the variant)
4. A structured list of extracted patients. Each patient includes:
   - patient_idx (integer index)
   - identifier (e.g., "Patient 1", "Proband", "II-3")
   - identifier_evidence_context (text snippet or "Pedigree Image")
5. Any pedigree description. Includes:
   - image_id (integer)
   - description (summary of family structure, affected status, genotype/segregation)

Your task:

For each patient, determine whether they carry one or more variants.  
Return **exactly** the following for each link:

- patient_idx  
- variant_id  
- zygosity: a single EvidenceBlock[Zygosity]  
- inheritance: a single EvidenceBlock[Inheritance]  
- testing_methods: a list of EvidenceBlock[TestingMethod] (max 2 items)  
- confidence: "high", "moderate", or "low"  

**EvidenceBlock rules:**

- Each EvidenceBlock must include:
  - value: the enum value
  - reasoning: human-readable explanation (required)
  - evidence_context: optional verbatim text from paper, possibly a table row.
  - table_id: optional index if evidence comes from a table
  - image_id: optional index if evidence comes from a figure/pedigree
- reasoning must always be present.
- At least one evidence source (text, table, or image) must be provided.
- Do not mix table_id and image_id in the same EvidenceBlock.

**Linking rules:**

- Only link if the patient is unambiguously reported to carry the variant.
- Evidence may come from:
  - Text sentences or consecutive sentences
  - Tables or structured lists
  - Pedigree images (image_id used)
- Do not infer links from generic references or biological plausibility.
- Negative genotypes (wild-type, homozygous reference, non-carrier) should not be linked.

**Confidence scoring:**

- "high": direct, explicit patient-level evidence
- "moderate": inferred from group/pedigree context, strong indirect support, patient membership unambiguous
- "low": partially ambiguous textual evidence; never for pure speculation

**Evidence handling:**

- For text or table evidence, provide verbatim quote in evidence_context.
- For pedigree evidence, evidence_context is null and image_id is set.
- Include reasoning for each EvidenceBlock explaining why it supports the value.
"""

agent = Agent(
    name='patient_variant_linker',
    instructions=INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=PatientVariantLinkerOutput,
)
