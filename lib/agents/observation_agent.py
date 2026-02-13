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


PROMPT = """
    - zygosity (one of "homozygous", "hemizygous", "heterozygous", "compound heterozygous", "unknown")
    - inheritance (one of "dominant", "recessive", "semi-dominant", "X-linked", "de novo", "somatic mosaicism", "mitochondrial", or "unknown")
    zygosity_evidence_context: Optional[str]
    inheritance_evidence_context: Optional[str]

    - zygosity_evidence_context: Exact text explicitly stating zygosity, if available.
    - inheritance_evidence_context: Exact text explicitly stating inheritance, if available.
    zygosity: Zygosity
    inheritance: Inheritance
"""
