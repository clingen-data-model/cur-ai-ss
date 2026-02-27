from enum import Enum
from typing import List, Optional

import requests
from agents import Agent, function_tool
from pydantic import BaseModel, model_validator
from typing_extensions import Self

from lib.evagg.utils.environment import env

ESEARCH_ENDPOINT = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
EFETCH_ENDPOINT = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi'


class TestingMethod(str, Enum):
    Chromosomal_microarray = 'Chromosomal microarray'
    Next_generation_sequencing_panels = 'Next generation sequencing panels'
    Exome_sequencing = 'Exome sequencing'
    Genome_sequencing = 'Genome sequencing'
    Sanger_sequencing = 'Sanger sequencing'
    Pcr = 'PCR'
    Homozygosity_mapping = 'Homozygosity mapping'
    Linkage_analysis = 'Linkage analysis'
    Genotyping = 'Genotyping'
    Denaturing_gradient_gel = 'Denaturing gradient gel'
    High_resolution_melting = 'High resolution melting'
    Restriction_digest = 'Restriction digest'
    Single_strand_conformation_polymorphism = 'Single-strand conformation polymorphism'
    Unknown = 'Unknown'
    Other = 'Other'


class PaperType(str, Enum):
    Letter = 'Letter'
    Research = 'Research'
    Case_series = 'Case_series'
    Case_study = 'Case_study'
    Cohort_analysis = 'Cohort_analysis'
    Case_control = 'Case_control'
    Unknown = 'Unknown'
    Other = 'Other'


class PaperExtractionOutput(BaseModel):
    title: str
    first_author: str
    journal_name: str | None
    abstract: str | None = None
    publication_year: int | None = None
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    testing_methods: List[TestingMethod]
    testing_methods_evidence: List[str | None]
    paper_types: List[PaperType]

    @model_validator(mode='after')
    def max_two_paper_types(self) -> Self:
        if len(self.paper_types) > 2:
            raise ValueError('paper_types must contain at most two items')
        return self

    @model_validator(mode='after')
    def max_two_methods(self) -> Self:
        if len(self.testing_methods) > 2:
            raise ValueError('testing_methods must contain at most two items')
        return self


@function_tool
def pubmed_search(title: str, first_author: str | None = None) -> List[str]:
    """
    Search PubMed using the esearch API.
    Returns:
    - A list of candidate PMIDs ordered by relevance.
    - Returns an empty list if no confident matches are found.
    - Does NOT return metadata.
    """
    terms = [f'{title}[ti]']

    if first_author:
        terms.append(f'{first_author}[au]')

    params: dict[str, str | int] = {
        'db': 'pubmed',
        'term': ' AND '.join(terms),
        'retmode': 'json',
        'sort': 'relevance',
        'retmax': 5,
    }

    r = requests.get(
        ESEARCH_ENDPOINT,
        params=params,
        timeout=10,
    )
    r.raise_for_status()

    data = r.json()
    return data.get('esearchresult', {}).get('idlist', [])


@function_tool
def pubmed_fetch_xml(pmid: str) -> str:
    """
    Fetch a PubMed record by PMID using efetch.

    Returns:
    - Raw PubMed XML for the specified PMID.
    - The PMID must come from PubMed search or the input text.
    """
    params = {
        'db': 'pubmed',
        'id': pmid,
        'retmode': 'xml',
    }

    r = requests.get(
        EFETCH_ENDPOINT,
        params=params,
        timeout=10,
    )
    r.raise_for_status()
    return r.text


PAPER_EXTRACTION_INSTRUCTIONS = """
You are an expert clinical data curator.

Input:
- Full text of an academic paper, case report, or registry entry.

Task Overview:

1. **Bibliographic Metadata Extraction**
   - Extract metadata directly from the text whenever explicitly present.
   - Fields to extract:
     - title
     - first_author
     - journal
     - abstract
     - publication_year
     - doi
     - pmid
     - pmcid
   - When a field cannot be confidently identified from the text or PubMed, fail rather than guessing.
   - Use PubMed search to find candidate PMIDs using the title and first author extracted from the text.
     - Do not use PubMed to discover or replace the title or first author unless they are genuinely missing or unreliable in the text.
     - PubMed may be trusted as authoritative for all other fields.
     - You should search using just the author's last name, then last name and first initial.
   - If a PMID is identified:
     - Fetch metadata from PubMed.
     - When PubMed XML is provided, extract fields using these locations:
       - title: MedlineCitation/Article/ArticleTitle
       - first_author: MedlineCitation/Article/AuthorList/Author[1]/LastName
       - journal: MedlineCitation/Article/Journal/ISOAbbreviation
       - abstract: MedlineCitation/Article/Abstract
       - publication_year: MedlineCitation/Article/Journal/JournalIssue/PubDate/Year
       - doi: PubmedData/ArticleIdList/ArticleId with IdType="doi"
       - pmcid: PubmedData/ArticleIdList/ArticleId with IdType="pmc"
     - Do not invent values.

2. **Top-Two Testing Method Selection**
  - From the list below, identify the **top two most relevant testing methods** used in the study.
  - Provide exact evidence text for each method.
  - Rules:
    - Select **at most two** methods.
    - Rank them in order of relevance (most relevant first).
    - Base relevance on what was actually used to generate the reported findings (not background methods or confirmatory-only assays).
    - Prefer explicitly stated methods in the text.
    - If multiple methods are mentioned, choose the two that contributed most directly to variant discovery or diagnosis.
    - If only one method is clearly described, return a single method.
    - If no method can be confidently determined, output `Unknown` for the method and `None` for evidence.
    - Do not invent or guess values.
  - Allowed methods:
    - Chromosomal_microarray – Genome-wide copy number analysis.
    - Next_generation_sequencing_panels – Targeted multi-gene NGS.
    - Exome_sequencing – Coding regions only (WES).
    - Genome_sequencing – Whole genome (WGS).
    - Sanger_sequencing – Capillary sequencing.
    - Pcr – PCR-based testing.
    - Homozygosity_mapping – Shared homozygous region analysis.
    - Linkage_analysis – Family-based locus mapping.
    - Genotyping – Predefined variant testing.
    - Denaturing_gradient_gel – DGGE variant detection.
    - High_resolution_melting – HRM variant detection.
    - Restriction_digest – Restriction enzyme assay.
    - Single_strand_conformation_polymorphism – SSCP variant detection.
    - Unknown – Method not stated.
    - Other – Method not listed.
  - Output format:
    - testing_methods: [<method_1>, <method_2>]
    - testing_methods_evidence: [<evidence method_1>, <evidence method_2>]

3. **Paper Type Selection**
 - Classify the paper into at MOST two of the following types:
   - Letter: Short correspondence or “Letter to the Editor”; brief report or commentary with limited data and minimal methodological detail.
   - Research: Full original research article presenting novel experimental, computational, or clinical findings with complete methods, results, and discussion.
   - Case_series: Descriptive report of multiple patients or families with shared phenotypes or variants, without a control group or formal statistical comparison.
   - Case_study: Detailed report of a single patient or a single family, often describing a rare phenotype or novel genetic variant.
   - Cohort_analysis: Observational analysis of a defined group of individuals selected by shared criteria, focusing on frequencies, outcomes, or genotype–phenotype correlations.
   - Case_control: Observational study comparing affected individuals (cases) to unaffected individuals (controls) to test genetic association or variant enrichment.
   - Unknown: The paper type cannot be confidently determined from the provided text.
   - Other: Does not fit the above categories (e.g., review, meta-analysis, guideline, methods, or database/resource paper).

Retry any tool requests (PubMed fetch or search) up to 3 times on an exponential delay.
"""

# --- Agent definition

agent = Agent(
    name='paper_extractor',
    instructions=PAPER_EXTRACTION_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=PaperExtractionOutput,
    tools=[pubmed_search, pubmed_fetch_xml],
)
