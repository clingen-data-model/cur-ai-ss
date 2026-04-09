from html import unescape
from re import sub
from typing import List

import requests
from agents import Agent, function_tool
from pydantic import BaseModel

from lib.core.environment import env
from lib.models import PaperExtractionOutput

ESEARCH_ENDPOINT = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
EFETCH_ENDPOINT = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi'


@function_tool
def pubmed_search(first_author: str) -> List[str]:
    """
    Broad PubMed search by first author only.
    Returns many candidate PMIDs for the agent to evaluate.
    """
    params: dict[str, str | int] = {
        'db': 'pubmed',
        'term': f'{first_author}[au]',
        'retmode': 'json',
        'sort': 'relevance',
        'retmax': 100,
    }

    if env.NCBI_API_KEY:
        params['api_key'] = env.NCBI_API_KEY
    if env.NCBI_EMAIL:
        params['email'] = env.NCBI_EMAIL

    r = requests.get(ESEARCH_ENDPOINT, params=params, timeout=10)
    r.raise_for_status()

    return r.json().get('esearchresult', {}).get('idlist', [])


@function_tool
def pubmed_fetch_xml(pmids: List[str]) -> str:
    """
    Fetch multiple PubMed records by PMID using efetch.
    Returns a single XML document containing all records.
    """
    if not pmids:
        return ''

    params = {
        'db': 'pubmed',
        'id': ','.join(pmids),
        'retmode': 'xml',
    }

    if env.NCBI_API_KEY:
        params['api_key'] = env.NCBI_API_KEY
    if env.NCBI_EMAIL:
        params['email'] = env.NCBI_EMAIL

    r = requests.get(EFETCH_ENDPOINT, params=params, timeout=30)
    r.raise_for_status()

    xml_text = unescape(r.text)
    xml_text = sub(r'</?(?:i|b|strong|sup|sub)>', '', xml_text)
    return xml_text


PAPER_EXTRACTION_INSTRUCTIONS = """
You are an expert clinical data curator.

Input:
- Full text of an academic paper, case report, or registry entry.

Task Overview:

1. Bibliographic Metadata Extraction
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
- When a field cannot be confidently identified, fail rather than guessing.
- Use PubMed in two phases: candidate generation and selection.

Candidate Generation:
- Call pubmed_search using ONLY the first_author extracted from the text.
- This will return many PMIDs for papers by this author.

Candidate Selection:
- Call pubmed_fetch_xml with all returned PMIDs in a single call.
- Compare the PubMed ArticleTitle of each record to the title extracted from the text.
- Select the PMID whose title best semantically matches the extracted title.
- Do NOT assume the first result is correct.
- Once the correct PMID is identified, extract all remaining metadata from that PubMed record.
    - title: MedlineCitation/Article/ArticleTitle 
    - first_author: MedlineCitation/Article/AuthorList/Author[1]/LastName 
    - journal: MedlineCitation/Article/Journal/ISOAbbreviation 
    - abstract: MedlineCitation/Article/Abstract 
    - publication_year: MedlineCitation/Article/Journal/JournalIssue/PubDate/Year 
    - doi: PubmedData/ArticleIdList/ArticleId with IdType="doi" 
    - pmcid: PubmedData/ArticleIdList/ArticleId with IdType="pmc"

2. **Paper Type Selection** - 
Classify the paper into at MOST two of the following types: 
    - Letter: Short correspondence or “Letter to the Editor”; brief report or commentary with limited data and minimal methodological detail. 
    - Research: Full original research article presenting novel experimental, computational, or clinical findings with complete methods, results, and discussion. 
    - Case_series: Descriptive report of multiple patients or families with shared phenotypes or variants, without a control group or formal statistical comparison. 
    - Case_study: Detailed report of a single patient or a single family, often describing a rare phenotype or novel genetic variant. 
    - Cohort_analysis: Observational analysis of a defined group of individuals selected by shared criteria, focusing on frequencies, outcomes, or genotype–phenotype correlations. 
    - Case_control: Observational study comparing affected individuals (cases) to unaffected individuals (controls) to test genetic association or variant enrichment. 
    - Unknown: The paper type cannot be confidently determined from the provided text. 
    - Other: Does not fit the above categories (e.g., review, meta-analysis, guideline, methods, or database/resource paper).
"""

# --- Agent definition

agent = Agent(
    name='paper_extractor',
    instructions=PAPER_EXTRACTION_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=PaperExtractionOutput,
    tools=[pubmed_search, pubmed_fetch_xml],
)
