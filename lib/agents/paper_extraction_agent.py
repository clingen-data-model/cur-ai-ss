from enum import Enum
from typing import List, Optional

import requests
from agents import Agent, function_tool
from pydantic import BaseModel

from lib.evagg.utils.environment import env

ESEARCH_ENDPOINT = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
EFETCH_ENDPOINT = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi'


class PaperExtractionOutput(BaseModel):
    title: str
    first_author: str
    journal_name: str | None
    abstract: str | None = None
    publication_year: int | None = None
    pmid: str | None = None
    pmcid: str | None = None
    doi: str | None = None


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
1. Extract bibliographic metadata directly from the text when explicitly present.
2. When a field cannot be confidently identified from either the text or PubMed,
   the task should fail rather than guessing.
3. Use PubMed search to find candidate PMIDs using title and author identified from the text.
4. If and only if a PMID is identified:
   - Use PubMed fetch to retrieve authoritative metadata.
   - When PubMed XML is provided:
     - Extract fields using these XML locations as guidance:
       - title: MedlineCitation/Article/ArticleTitle
       - first_author: MedlineCitation/Article/AuthorList/Author[1]/LastName
       - journal: MedlineCitation/Article/Journal/ISOAbbreviation
       - abstract: MedlineCitation/Article/Abstract
       - pub_year: MedlineCitation/Article/Journal/JournalIssue/PubDate/Year
       - doi: PubmedData/ArticleIdList/ArticleId with IdType="doi"
       - pmcid: PubmedData/ArticleIdList/ArticleId with IdType="pmc"
   - Do not invent values.

More Context:
- The title and first author should almost always be extracted directly
  from the paper text.
- Do not use PubMed to discover or replace the title or first author unless
  they are genuinely missing or cannot be reliably determined from the text.
- PubMed may be trusted as authoritative for the other fields.
- Retry the tool requests up to 3 times on an exponential delay.
"""

# --- Agent definition

agent = Agent(
    name='paper_extractor',
    instructions=PAPER_EXTRACTION_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=PaperExtractionOutput,
    tools=[pubmed_search, pubmed_fetch_xml],
)
