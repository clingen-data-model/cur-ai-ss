import pytest

from lib.evagg.ref import NcbiLookupClient
from lib.evagg.utils import RequestsWebContentClient
from lib.evagg.types import Paper


@pytest.fixture
def mock_web_client(mock_client):
    return mock_client(RequestsWebContentClient)


def test_single_gene_direct(mock_web_client):
    web_client = mock_web_client('ncbi_symbol_single.json')
    result = NcbiLookupClient(web_client).gene_id_for_symbol('FAM111B')
    assert result == {'FAM111B': 374393}


def test_single_gene_indirect(mock_web_client):
    web_client = mock_web_client(*(['ncbi_symbol_synonym.json'] * 3))

    result = NcbiLookupClient(web_client).gene_id_for_symbol('FEB11')
    assert result == {}

    result = NcbiLookupClient(web_client).gene_id_for_symbol(
        'FEB11', allow_synonyms=True
    )
    assert result == {'FEB11': 57094}

    # Verify that this would also work for the direct match.
    result = NcbiLookupClient(web_client).gene_id_for_symbol('CPA6')
    assert result == {'CPA6': 57094}


def test_single_gene_miss(mock_web_client):
    web_client = mock_web_client({})
    result = NcbiLookupClient(web_client).gene_id_for_symbol('FAM11B')
    assert result == {}

    web_client = mock_web_client('ncbi_symbol_single.json')
    result = NcbiLookupClient(web_client).gene_id_for_symbol('not a gene')
    assert result == {}


def test_multi_gene(mock_web_client):
    web_client = mock_web_client(*(['ncbi_symbol_multi.json'] * 3))

    result = NcbiLookupClient(web_client).gene_id_for_symbol('FAM111B', 'FEB11')
    assert result == {'FAM111B': 374393}

    result = NcbiLookupClient(web_client).gene_id_for_symbol(
        'FAM111B', 'FEB11', allow_synonyms=True
    )
    assert result == {'FAM111B': 374393, 'FEB11': 57094}

    result = NcbiLookupClient(web_client).gene_id_for_symbol(
        'FAM111B', 'FEB11', 'not a gene', allow_synonyms=True
    )
    assert result == {'FAM111B': 374393, 'FEB11': 57094}


def test_variant(mock_web_client):
    web_client = mock_web_client(*(['efetch_snp_single_variant.xml'] * 3))

    result = NcbiLookupClient(web_client).hgvs_from_rsid('rs146010120')
    assert result == {
        'rs146010120': {
            'hgvs_c': 'NM_001276.4:c.104G>A',
            'hgvs_p': 'NP_001267.2:p.Arg35Gln',
            'hgvs_g': 'NC_000001.11:g.203185337C>T',
            'gene': 'CHI3L1',
        }
    }


def test_multi_variant(mock_web_client):
    web_client = mock_web_client('efetch_snp_multi_variant.xml')

    result = NcbiLookupClient(web_client).hgvs_from_rsid('rs146010120', 'rs113488022')
    assert result == {
        'rs113488022': {
            'hgvs_p': 'NP_004324.2:p.Val600Gly',
            'hgvs_c': 'NM_004333.6:c.1799T>G',
            'hgvs_g': 'NC_000007.14:g.140753336A>C',
            'gene': 'BRAF',
        },
        'rs146010120': {
            'hgvs_p': 'NP_001267.2:p.Arg35Gln',
            'hgvs_c': 'NM_001276.4:c.104G>A',
            'hgvs_g': 'NC_000001.11:g.203185337C>T',
            'gene': 'CHI3L1',
        },
    }


def test_missing_variant(mock_web_client):
    web_client = mock_web_client(None)

    result = NcbiLookupClient(web_client).hgvs_from_rsid('rs123456789')
    assert result == {'rs123456789': {}}


def test_non_rsid(mock_web_client):
    web_client = mock_web_client('')

    with pytest.raises(ValueError):
        NcbiLookupClient(web_client).hgvs_from_rsid('not a rsid')
    with pytest.raises(ValueError):
        NcbiLookupClient(web_client).hgvs_from_rsid('rs1a2b')
    with pytest.raises(ValueError):
        NcbiLookupClient(web_client).hgvs_from_rsid('12345')


def test_pubmed_search(mock_web_client):
    web_client = mock_web_client('esearch_pubmed_gene_CPA6.xml')
    result = NcbiLookupClient(web_client).search('CPA6')
    assert result == ['24290490']


def test_pubmed_fetch(mock_web_client, json_load):
    web_client = mock_web_client('efetch_pubmed_paper_24290490.xml')
    result = NcbiLookupClient(web_client).fetch('24290490', b'mock fulltext')
    assert result and Paper(
        id='pmid:24290490',
        title='Increased CPA6 promoter methylation in focal epilepsy and in febrile seizures.',
        abstract=(
            'Focal epilepsy (FE) is one of the most common forms of adult epilepsy and is usually '
            'regarded as a multifactorial disorder. Febrile seizures (FS) often appear during '
            'childhood in a subtype of FE patients, i.e. with temporal lobe epilepsy (TLE) and '
            'hippocampal sclerosis (HS). FS are the most common human convulsive event associated '
            'with fever. Genetic evidences for FS have suggested a complex mode of inheritance. '
            'Until now, to investigate genes at the genomic level, linkage analysis of familial '
            'forms and association studies have been performed, but nothing conclusive has been '
            'clearly related to FE and FS. As complex disorders, environmental factors might play '
            'a crucial role through epigenetic modification of key candidate genes such as CPA6, '
            'which encodes Carboxypeptidase A6, an extracellular protein. Therefore, we assessed '
            'DNA methylation in promoter of CPA6. In 186 FE patients and 92 FS patients compared '
            'to 93 healthy controls and 42 treated controls with antiepileptic drugs (AEDs), we '
            'found significant higher levels of methylation for epileptic patients. Methylation '
            'status were 3.4% (±3.2%) for FE cases and 4.3% (±3.5%) for FS cases, whereas healthy '
            'individuals and treated controls with AEDs showed a level of 0.8% (±2.9%) and 1.5% '
            '(±3.9%), respectively (p≤0.001 for all comparisons). These results let growing '
            'evidence for DNA methylation involvment in FE and FS. Copyright © 2013 Elsevier B.V. '
            'All rights reserved.'
        ),
        journal='Epilepsy Res',
        first_author='Belhedi',
        pub_year='2014',
        doi='10.1016/j.eplepsyres.2013.10.007',
        pmid='24290490',
        pmcid='',
        citation='Belhedi (2014) Epilepsy Res',
        can_access=False,
        license='unknown',
        OA=False,
        link='https://pubmed.ncbi.nlm.nih.gov/24290490/',
        content=b'mock fulltext',
    )


def test_pubmed_pmc_oa_fetch(mock_web_client):
    web_client = mock_web_client(
        'efetch_pubmed_paper_31427284.xml', 'ncbi_pmc_is_oa_PMC6824399.xml'
    )
    result = NcbiLookupClient(web_client).fetch('31427284', b'mock fulltext')
    assert result and result.can_access is False


def test_pubmed_fetch_missing(mock_web_client, xml_parse):
    web_client = mock_web_client(None)
    result = NcbiLookupClient(web_client).fetch('7777777777777777', 'mock fulltext')
    assert result is None
    web_client = mock_web_client(xml_parse('<PubmedArticleSet></PubmedArticleSet>'))
    result = NcbiLookupClient(web_client).fetch('7777777777777777', 'mock fulltext')
    assert result is None
