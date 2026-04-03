from enum import Enum
from html import unescape
from re import split, sub
from typing import List, Optional

import requests
from agents import Agent, function_tool
from pydantic import BaseModel

from lib.core.environment import env
from lib.models import PaperExtractionOutput

ESEARCH_ENDPOINT = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
EFETCH_ENDPOINT = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi'


@function_tool
def pubmed_search(title: str, first_author: str | None = None) -> List[str]:
    """
    Minimal deterministic PubMed title search.
    """
    tokens = split(r'\s+', title.strip())

    terms = [f'{t}[ti]' for t in tokens if t]

    if first_author:
        terms.append(f'{first_author}[au]')

    params: dict[str, str | int] = {
        'db': 'pubmed',
        'term': ' AND '.join(terms),
        'retmode': 'json',
        'sort': 'relevance',
        'retmax': 5,
    }

    if env.NCBI_API_KEY:
        params['api_key'] = env.NCBI_API_KEY
    if env.NCBI_EMAIL:
        params['email'] = env.NCBI_EMAIL

    r = requests.get(ESEARCH_ENDPOINT, params=params, timeout=10)
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

    if env.NCBI_API_KEY:
        params['api_key'] = env.NCBI_API_KEY
    if env.NCBI_EMAIL:
        params['email'] = env.NCBI_EMAIL

    r = requests.get(
        EFETCH_ENDPOINT,
        params=params,
        timeout=10,
    )
    r.raise_for_status()

    # Strip formatting html out of response.
    # NB: there might be better ways to do this going forwards, especially
    # if we want to preserve subscripts!
    xml_text = unescape(r.text)
    xml_text = sub(r'</?(?:i|b|strong|sup|sub)>', '', xml_text)
    return xml_text


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
     - If the initial search returns no results:
        1. Modify the title to remove common stop words (a, an, the, etc.) and search with that modified title + last name of the original author.
        2. Only if that fails, search using author permutations (last name, last name + first initial).
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
     - Return and do not try to search further.

2. **Paper Type Selection**
 - Classify the paper into at MOST two of the following types:
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
