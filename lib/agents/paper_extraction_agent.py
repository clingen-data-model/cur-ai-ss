from html import unescape
from re import sub
from typing import List, Tuple
from xml.etree import ElementTree as ET

import requests
from agents import Agent, function_tool
from pydantic import BaseModel

from lib.core.environment import env
from lib.models import PaperExtractionOutput

ESEARCH_ENDPOINT = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
EFETCH_ENDPOINT = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi'


@function_tool
def pubmed_search_and_titles(
    first_author: str, gene_symbol: str
) -> List[Tuple[str, str]]:
    """
    Search PubMed by first author and optionally gene symbol, then fetch titles.
    Returns a list of (pmid, title) tuples for candidate selection.
    """
    # Phase 1: search by author and gene
    search_terms = [f'{first_author}[au]', gene_symbol]
    search_query = ' AND '.join(search_terms)
    params: dict[str, str | int] = {
        'db': 'pubmed',
        'term': search_query,
        'retmode': 'json',
        'sort': 'relevance',
        'retmax': 50,
    }
    if env.NCBI_API_KEY:
        params['api_key'] = env.NCBI_API_KEY
    if env.NCBI_EMAIL:
        params['email'] = env.NCBI_EMAIL

    r = requests.get(ESEARCH_ENDPOINT, params=params, timeout=10)
    r.raise_for_status()
    pmids = r.json().get('esearchresult', {}).get('idlist', [])
    if not pmids:
        return []

    # Phase 2: fetch titles
    fetch_params = {
        'db': 'pubmed',
        'id': ','.join(pmids),
        'retmode': 'xml',
    }
    if env.NCBI_API_KEY:
        fetch_params['api_key'] = env.NCBI_API_KEY
    if env.NCBI_EMAIL:
        fetch_params['email'] = env.NCBI_EMAIL

    r = requests.get(EFETCH_ENDPOINT, params=fetch_params, timeout=30)
    r.raise_for_status()

    # Extract PMIDs and titles
    root = ET.fromstring(r.text)
    results = []
    for article in root.findall('.//PubmedArticle'):
        pmid_elem = article.find('./MedlineCitation/PMID')
        title_elem = article.find('./MedlineCitation/Article/ArticleTitle')

        # Skip if no PMID or empty
        if pmid_elem is None or not pmid_elem.text:
            continue

        pmid_text: str = pmid_elem.text
        title_text = ''.join(title_elem.itertext()) if title_elem is not None else ''
        results.append((pmid_text, title_text))

    return results


@function_tool
def pubmed_fetch_one(pmid: str) -> str:
    """
    Fetch a single PubMed record by PMID using efetch.
    Returns XML text for that record.
    """
    if not pmid:
        return ''

    params = {
        'db': 'pubmed',
        'id': pmid,
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
- Gene symbol for the paper
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

Candidate Generation & Selection Workflow:

1️⃣ Candidate Generation:
- Call `pubmed_search_and_titles` with the `first_author` extracted from the text and the passed in gene_symbol.
- This will return a list of `(pmid, title)` tuples for candidate papers by this author about this gene.

2️⃣ Candidate Selection:
- Compare each returned title to the `title` extracted from the text.
- Determine the PMID whose title is most closely aligned (semantic match or exact match).
- Do NOT assume the first result is correct.

3️⃣ Metadata Fetching:
- Call `pubmed_fetch_one` on the selected PMID to fetch the full PubMed XML.
- Extract all remaining metadata from that PubMed record:
    - title: MedlineCitation/Article/ArticleTitle 
    - first_author: MedlineCitation/Article/AuthorList/Author[1]/LastName 
    - journal: MedlineCitation/Article/Journal/ISOAbbreviation 
    - abstract: MedlineCitation/Article/Abstract 
    - publication_year: MedlineCitation/Article/Journal/JournalIssue/PubDate/Year 
    - doi: PubmedData/ArticleIdList/ArticleId with IdType="doi" 
    - pmcid: PubmedData/ArticleIdList/ArticleId with IdType="pmc"

-2. **Paper Type Selection** -
Classify the paper into at MOST two of the following types:
    - Letter: Short correspondence or “Letter to the Editor”; brief report or commentary with limited data and minimal methodological detail.
    - Research: Full original research article presenting novel experimental, computational, or clinical findings with complete methods, results, and discussion.
    - Case_series: Descriptive report of multiple patients or families with shared phenotypes or variants, without a control group or formal statistical comparison.
    - Case_study: Detailed report of a single patient or a single family, often describing a rare phenotype or novel genetic variant.
    - Cohort_analysis: Observational analysis of a defined group of individuals selected by shared criteria, focusing on frequencies, outcomes, or genotype–phenotype correlations.
    - Case_control: Observational study comparing affected individuals (cases) to unaffected individuals (controls) to test genetic association or variant enrichment.
    - Unknown: The paper type cannot be confidently determined from the provided text.
    - Other: Does not fit the above categories (e.g., review, meta-analysis, guideline, methods, or database/resource paper).

Important Guidelines:
- When a field cannot be confidently identified, fail rather than guess.
- Always use the `(pmid, title)` pairs to deterministically select the correct PubMed record.
- Only fetch full records for the chosen PMID.
"""

# --- Agent definition
agent = Agent(
    name='paper_extractor',
    instructions=PAPER_EXTRACTION_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=PaperExtractionOutput,
    tools=[pubmed_search_and_titles, pubmed_fetch_one],
)
