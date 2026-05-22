from html import unescape
from re import sub
from typing import List, Tuple
from xml.etree import ElementTree as ET

import requests
from agents import Agent, function_tool
from pydantic import BaseModel

from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
from lib.core.environment import env
from lib.models import PaperExtractionOutput

ESEARCH_ENDPOINT = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
EFETCH_ENDPOINT = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi'


@function_tool
def pubmed_search_and_titles(
    first_author: str, search_term: str = ''
) -> List[Tuple[str, str]]:
    """
    Search PubMed by first author and optional search term (gene, keyword, year, etc).
    Returns a list of (pmid, title) tuples for candidate selection.
    """
    if search_term:
        search_query = f'{first_author}[au] AND {search_term}'
    else:
        search_query = f'{first_author}[au]'

    params: dict[str, str | int] = {
        'db': 'pubmed',
        'term': search_query,
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
    pmids = r.json().get('esearchresult', {}).get('idlist', [])

    if not pmids:
        return []

    # Fetch titles
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

CONTEXT:
- The paper text and gene symbol are provided above in the PAPER AND GENE CONTEXT section.

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

1️⃣ Gene Extraction:
- Attempt to extract the gene symbol or gene name from the abstract as it appears in the paper.
- This is the form of the gene that the authors use when discussing this paper.
- If the gene is NOT mentioned in the abstract, use the Gene symbol provided in the input.

2️⃣ Four-Phase PubMed Search:
Use a four-phase search strategy, collecting candidates from each phase in order:

**Phase 1: Author + Gene Search**
- Call `pubmed_search_and_titles` with the `first_author` and gene_symbol (either extracted from abstract or provided).
- Save these results as top candidates.

**Phase 2: Author + Non-Gene Key Word from Title Search**
- Identify the most information-rich word from the extracted title that is NOT a gene (diseases, phenotypes, anatomical terms, or other key concepts).
- Evaluate the title to choose the word that best captures the paper's main topic besides the gene.
- Call `pubmed_search_and_titles` with the `first_author` and this key word.
- These results provide broader coverage beyond just the gene symbol.

**Phase 3: Author + Publication Year Search**
- Extract the publication year from the metadata.
- Call `pubmed_search_and_titles` with the `first_author` and the publication year.
- This significantly narrows down candidates by temporal proximity.

**Phase 4: Author-Only Search**
- If phases 1-3 do not yield good matches, perform a broad search using only author name.
- Call `pubmed_search_and_titles` with just the `first_author` (empty search_term).
- This provides maximum breadth as a final fallback.

3️⃣ Candidate Selection:
- Compare each returned title to the `title` extracted from the text.
- Look for semantic matches (same keywords, topics, genes) not just exact string matches.
- Determine the PMID whose title is most closely aligned to the extracted title.
- **Prioritize Phase 1 results, but do not discard results from later phases if they provide better title matches.**
- When in doubt, prefer results from earlier phases (author+gene > author+keyword > author+year > author-only).

4️⃣ Metadata Fetching:
- Call `pubmed_fetch_one` on the selected PMID to fetch the full PubMed XML.
- Extract all remaining metadata from that PubMed record:
    - title: MedlineCitation/Article/ArticleTitle
    - first_author: MedlineCitation/Article/AuthorList/Author[1]/LastName
    - journal: MedlineCitation/Article/Journal/ISOAbbreviation
    - abstract: MedlineCitation/Article/Abstract
    - publication_year: MedlineCitation/Article/Journal/JournalIssue/PubDate/Year
    - doi: PubmedData/ArticleIdList/ArticleId with IdType=”doi”
    - pmcid: PubmedData/ArticleIdList/ArticleId with IdType=”pmc”

2. **Paper Type Selection**
Classify the paper into at MOST two of the following types:
    - Letter: Short correspondence or “Letter to the Editor”; brief report or commentary with limited data and minimal methodological detail.
    - Research: Full original research article presenting novel experimental, computational, or clinical findings with complete methods, results, and discussion.
    - Case_series: Descriptive report of multiple patients or families with shared phenotypes or variants, without a control group or formal statistical comparison.
    - Case_study: Detailed report of a single patient or a single family, often describing a rare phenotype or novel genetic variant.
    - Cohort_analysis: Observational analysis of a defined group of individuals selected by shared criteria, focusing on frequencies, outcomes, or genotype–phenotype correlations.
    - Case_control: Observational study comparing affected individuals (cases) to unaffected individuals (controls) to test genetic association or variant enrichment.
    - Unknown: The paper type cannot be confidently determined from the provided text.
    - Other: Does not fit the above categories (e.g., review, meta-analysis, guideline, methods, or database/resource paper).

3. **Gene-Disease Relationship Extraction**
Extract the disease name and mode of inheritance associated with this gene in the paper:
- **disease_name**: The name or description of the disease/phenotype caused by variants in this gene (e.g., "Stargardt disease", "retinitis pigmentosa", "dilated cardiomyopathy"). Extract from the abstract, introduction, or case descriptions.
- **disease_inheritance_mode**: The primary mode of inheritance for this gene-disease relationship as stated or implied in the paper (e.g., "Autosomal Recessive", "Autosomal Dominant", "X-linked Recessive"). Extract from the abstract or clinical findings.
- Include reasoning that identifies where in the paper this information was found.
- If the disease name or inheritance mode cannot be confidently identified, omit the gene_disease_relation field entirely.

Important Guidelines:
- When a field cannot be confidently identified, fail rather than guess.
- Always use the `(pmid, title)` pairs to deterministically select the correct PubMed record.
- Only fetch full records for the chosen PMID.
- Prefer the gene form as it appears in the abstract. Only use the provided gene symbol if the gene is not mentioned in the abstract.
"""

PAPER_EXTRACTION_AGENT_INSTRUCTIONS = PAPER_EXTRACTION_INSTRUCTIONS

agent = Agent(
    name='paper_extractor',
    instructions=BASE_SYSTEM_INSTRUCTIONS,
    model=env.OPENAI_API_DEPLOYMENT,
    output_type=PaperExtractionOutput,
    tools=[pubmed_search_and_titles, pubmed_fetch_one],
)
