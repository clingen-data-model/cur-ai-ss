import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from defusedxml import ElementTree
from requests.exceptions import HTTPError, RetryError

from lib.evagg.types import Paper
from lib.evagg.utils.environment import env
from lib.evagg.utils import RequestsWebContentClient


logger = logging.getLogger(__name__)


class NcbiClientBase:
    EUTILS_HOST = 'https://eutils.ncbi.nlm.nih.gov'
    EUTILS_SEARCH_SITE = '/entrez/eutils/esearch.fcgi'
    EUTILS_FETCH_SITE = '/entrez/eutils/efetch.fcgi'

    def __init__(
        self,
        web_client: RequestsWebContentClient,
    ) -> None:
        self._web_client = web_client

    @property
    def credential_params(self) -> dict[str, str]:
        return (
            {'email': env.NCBI_EUTILS_EMAIL, 'api_key': env.NCBI_EUTILS_API_KEY}
            if env.NCBI_EUTILS_EMAIL and env.NCBI_EUTILS_API_KEY
            else {}
        )

    def _esearch(self, db: str, term: str, sort: str, **kwargs: Any) -> Any:
        params = {'db': db, 'term': term, 'sort': sort, 'tool': 'biopython'}
        return self._web_client.get(
            f'{self.EUTILS_HOST}{self.EUTILS_SEARCH_SITE}',
            params={
                **self.credential_params,
                **params,
                **kwargs,
            },
            content_type='xml',
        )

    def _efetch(
        self,
        db: str,
        id: str,
        retmode: str | None = None,
        rettype: str | None = None,
        **kwargs: Any,
    ) -> Any:
        params = {'db': db, 'id': id, 'tool': 'biopython'}
        if retmode:
            params['retmode'] = retmode
        if rettype:
            params['rettype'] = rettype
        return self._web_client.get(
            f'{self.EUTILS_HOST}{self.EUTILS_FETCH_SITE}',
            params={
                **self.credential_params,
                **params,
                **kwargs,
            },
            content_type=retmode,
        )


class NcbiLookupClient(
    NcbiClientBase,
):
    """A client for querying the various services in the NCBI API."""

    # According to https://support.nlm.nih.gov/knowledgebase/article/KA-05316/en-us the max
    # RPS for NCBI API endpoints is 3 without an API key, and 10 with an API key.
    SYMBOL_GET_URL = 'https://api.ncbi.nlm.nih.gov/datasets/v2alpha/gene/symbol/{symbols}/taxon/Human'
    PMCOA_GET_URL = 'https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={pmcid}'
    BIOC_GET_URL = 'https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_xml/{pmcid}/ascii'

    def __init__(
        self,
        web_client: RequestsWebContentClient,
    ) -> None:
        super().__init__(web_client)

    def _get_xml_props(self, article: Any) -> Dict[str, str]:
        """Extracts paper properties from an XML root element."""
        extractions = {
            'title': './MedlineCitation/Article/ArticleTitle',
            'abstract': './MedlineCitation/Article/Abstract',
            'journal': './MedlineCitation/Article/Journal/ISOAbbreviation',
            'first_author': './MedlineCitation/Article/AuthorList/Author[1]/LastName',
            'pub_year': './MedlineCitation/Article/Journal/JournalIssue/PubDate/Year',
            'doi': "./PubmedData/ArticleIdList/ArticleId[@IdType='doi']",
            'pmcid': "./PubmedData/ArticleIdList/ArticleId[@IdType='pmc']",
        }

        def _get_xml_string(node: Any) -> str:
            return (
                ' '.join((''.join(node.itertext())).split()) if node is not None else ''
            )

        props = {
            k: _get_xml_string(article.find(path)) for k, path in extractions.items()
        }
        return props

    def _get_license_props(self, pmcid: str) -> Dict[str, str | bool]:
        """Get the access status for a paper from the PMC OA API."""
        props: Dict[str, str | bool] = {
            'can_access': False,
            'license': 'unknown',
            'OA': False,
        }
        if not pmcid:
            return props

        # Do a record lookup for the given pmcid at the PMC OA endpoint.
        root = self._web_client.get(
            self.PMCOA_GET_URL.format(pmcid=pmcid), content_type='xml'
        )
        # Look for a record with the given pmcid in the response.
        record = root.find(f"records/record[@id='{pmcid}']")

        if record is None:
            # No valid OA record returned - if there is an error code, extract it from the response.
            err_code = (
                root.find('error').attrib['code']
                if root.find('error') is not None
                else None
            )
            if err_code == 'idIsNotOpenAccess':
                props['license'] = 'not_open_access'
            elif err_code:
                logger.warning(f'Unexpected PMC OA error for PMCID {pmcid}: {err_code}')
        else:
            props['can_access'] = True
            props['license'] = license = record.attrib.get('license', 'unknown')
            props['OA'] = True
            if '-ND' in license:
                # If it has a "no derivatives" license, then we don't consider it open access.
                logger.debug(
                    f'PMC OA record found for {pmcid} but has a no-derivatives license: {license}'
                )
                props['can_access'] = False

        return props

    def _get_derived_props(self, props: Dict[str, Any]) -> Dict[str, str]:
        """Get the derived properties of a paper."""
        derived_props: Dict[str, Any] = {}
        derived_props['citation'] = (
            f'{props["first_author"]} ({props["pub_year"]}) {props["journal"]}'
        )
        derived_props['link'] = f'https://pubmed.ncbi.nlm.nih.gov/{props["pmid"]}/'
        return derived_props

    def search(self, query: str, **extra_params: Dict[str, Any]) -> Sequence[str]:
        root = self._esearch(db='pubmed', term=query, sort='relevance', **extra_params)
        pmids = [
            pmid_elem.text
            for pmid_elem in root.findall('./IdList/Id')
            if pmid_elem.text
        ]
        return pmids

    def fetch(self, paper_id: str) -> Optional[Paper]:
        if (
            root := self._efetch(
                db='pubmed', id=paper_id, retmode='xml', rettype='abstract'
            )
        ) is None:
            return None

        if (
            article := root.find(
                f"PubmedArticle/MedlineCitation/PMID[.='{paper_id}']/../.."
            )
        ) is None:
            return None

        props: Dict[str, Any] = {
            'id': f'pmid:{paper_id}',
            'pmid': paper_id,
        }
        props.update(self._get_xml_props(article))
        props.update(self._get_license_props(props['pmcid']))
        props.update(self._get_derived_props(props))
        return Paper(**props)

    def gene_id_for_symbol(
        self, *symbols: str, allow_synonyms: bool = False
    ) -> Dict[str, int]:
        """Query the NCBI gene database for the gene_id for a given collection of `symbols`.

        If `allow_synonyms` is True, then this will attempt to return the most relevant gene_id for each symbol. If
        there are multiple matches to a symbol, the direct match (where the query symbol is the official symbol) will
        be returned. If there are no direct matches, then the first synonym match will be returned.
        """
        url = self.SYMBOL_GET_URL.format(symbols=','.join(symbols))
        root = self._web_client.get(url, content_type='json')
        return _extract_gene_symbols(root.get('reports', []), symbols, allow_synonyms)

    def hgvs_from_rsid(self, *rsids: str) -> Dict[str, Dict[str, str]]:
        # Provided rsids should be numeric strings prefixed with `rs`.
        if not rsids or not all(
            rsid.startswith('rs') and rsid[2:].isnumeric() for rsid in rsids
        ):
            raise ValueError(
                "Invalid rsids list - must provide 'rs' followed by a string of numeric characters."
            )

        uids = {rsid[2:] for rsid in rsids}
        try:
            root = self._efetch(
                db='snp', id=','.join(uids), retmode='xml', rettype='xml'
            )
        except HTTPError as e:
            logger.warning(
                f'Unexpected error fetching HGVS data for rsids {",".join(uids)}: {e}'
            )
            return {}

        return {'rs' + uid: _extract_hgvs_from_xml(root, uid) for uid in uids}


def _extract_hgvs_from_xml(root: Any, uid: str) -> Dict[str, str]:
    if root is None:
        return {}
    ns = '{https://www.ncbi.nlm.nih.gov/SNP/docsum}'
    # Find the first DOCSUM node under a DocumentSummary with the given rsid in the document hierarchy.
    node = next(
        iter(root.findall(f"./{ns}DocumentSummary[@uid='{uid}']/{ns}DOCSUM")), None
    )
    if node is None or not node.text:
        return {}

    # Extract all key/value pairs from node text of the form 'key=value|key=value|...' into a dict.
    props = {
        k: v
        for k, v in (
            kvp.split('=') for kvp in (node.text or '').split('|') if '=' in kvp
        )
        if k and v
    }
    # Extract all values from the HGVS property of the form 'HGVS=value1,value2...'.
    hgvs = props.get('HGVS', '').split(',')
    gene = props.get('GENE', '').split(':')[0]

    # Return a dict with the first occurrence of each value that starts with 'NP_' (hgvs_p), 'NM_' (hgvs_c), or 'NC_'
    # (genomic reference sequences / non-coding variants).
    types = {
        'hgvs_p': lambda x: x.startswith('NP_'),
        'hgvs_c': lambda x: x.startswith('NM_'),
        'hgvs_g': lambda x: x.startswith('NC_'),
    }
    ret_dict = {
        k: next(filter(match, hgvs))
        for k, match in types.items()
        if (any(map(match, hgvs)))
    }
    ret_dict['gene'] = gene
    return ret_dict


def _extract_gene_symbols(
    reports: List[Dict], symbols: Sequence[str], allow_synonyms: bool
) -> Dict[str, int]:
    matches = {
        g['gene']['symbol']: int(g['gene']['gene_id'])
        for g in reports
        if g['gene']['symbol'] in symbols
    }

    if allow_synonyms:
        for missing_symbol in [s for s in symbols if s not in matches.keys()]:
            if synonym := next(
                (g['gene'] for g in reports if missing_symbol in g['query']), None
            ):
                matches[missing_symbol] = int(synonym['gene_id'])

    return matches


def get_ncbi_response_translator() -> Callable[[str, int, str], Tuple[int, str]]:
    def translate(url: str, original_status: int, text: str) -> Tuple[int, str]:
        """Translate the status code of an NCBI search response in case they improperly reported a server error."""
        if (
            text
            and original_status == 200
            and url.startswith(
                NcbiClientBase.EUTILS_HOST + NcbiClientBase.EUTILS_SEARCH_SITE
            )
            and (error := ElementTree.fromstring(text).find('ERROR')) is not None
        ):
            # Extract error code by returning the first occurrence of an integer between 400 and 600 in the error text.
            status = next(
                (
                    int(s)
                    for s in (error.text or '').split()
                    if s.isnumeric() and 400 <= int(s) < 600
                ),
                500,
            )
            logger.warning(
                f'NCBI esearch request failed with status {status}: {error.text}'
            )
            return status, text
        return original_status, text

    return translate
