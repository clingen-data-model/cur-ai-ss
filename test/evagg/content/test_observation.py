import asyncio
from typing import Any

import pytest

from lib.evagg.content import HGVSVariantComparator, ObservationFinder
from lib.evagg.content.variant import HGVSVariantFactory
from lib.evagg.llm import OpenAIClient
from lib.evagg.types import HGVSVariant, Paper


@pytest.fixture
def paper(json_load: Any) -> Paper:
    paper = Paper(
        **{
            'id': 'pmid:28554332',
            'pmid': '28554332',
            'title': 'Genomic diagnosis for children with intellectual disability and/or developmental delay.',
            'abstract': 'Developmental disabilities have diverse genetic causes that must be identified to facilitate precise diagnoses. We describe genomic data from 371 affected individuals, 309 of which were sequenced as proband-parent trios.Whole-exome sequences (WES) were generated for 365 individuals (127 affected) and whole-genome sequences (WGS) were generated for 612 individuals (244 affected).Pathogenic or likely pathogenic variants were found in 100 individuals (27%), with variants of uncertain significance in an additional 42 (11.3%). We found that a family history of neurological disease, especially the presence of an affected first-degree relative, reduces the pathogenic/likely pathogenic variant identification rate, reflecting both the disease relevance and ease of interpretation of de novo variants. We also found that improvements to genetic knowledge facilitated interpretation changes in many cases. Through systematic reanalyses, we have thus far reclassified 15 variants, with 11.3% of families who initially were found to harbor a VUS and 4.7% of families with a negative result eventually found to harbor a pathogenic or likely pathogenic variant. To further such progress, the data described here are being shared through ClinVar, GeneMatcher, and dbGaP.Our data strongly support the value of large-scale sequencing, especially WGS within proband-parent trios, as both an effective first-choice diagnostic tool and means to advance clinical and research progress related to pediatric neurological disease.',
            'journal': 'Genome Med',
            'first_author': 'Bowling',
            'pub_year': '2017',
            'doi': '10.1186/s13073-017-0433-1',
            'pmcid': 'PMC5448144',
            'can_access': True,
            'license': 'CC BY',
            'citation': 'Bowling (2017) Genome Med',
            'link': 'https://pubmed.ncbi.nlm.nih.gov/28554332/',
            'fulltext_xml': '<document><id>5448144</id><infon key="license">CC BY</infon><passage><infon key="article-id_doi">10.1186/s13073-017-0433-1</infon><infon key="article-id_pmc">5448144</infon><infon key="article-id_pmid">28554332</infon><infon key="article-id_publisher-id">433</infon><infon key="elocation-id">43</infon><infon key="kwd">Developmental delay Intellectual disability De novo Clinical sequencing CSER</infon><infon key="license">\\nOpen AccessThis article is distributed under the terms of the Creative Commons Attribution 4.0 International License (http://creativecommons.org/licenses/by/4.0/), which permits unrestricted use, distribution, and reproduction in any medium, provided you give appropriate credit to the original author(s) and the source, provide a link to the Creative Commons license, and indicate if changes were made. The Creative Commons Public Domain Dedication waiver (http://creativecommons.org/publicdomain/zero/1.0/) applies to the data made available in this article, unless otherwise stated.</infon><infon key="name_0">surname:Bowling;given-names:Kevin M.</infon><infon key="name_1">surname:Thompson;given-names:Michelle L.</infon><infon key="name_10">surname:Kelley;given-names:Whitley V.</infon><infon key="name_11">surname:Lamb;given-names:Neil E.</infon><infon key="name_12">surname:Lose;given-names:Edward J.</infon><infon key="name_13">surname:Rich;given-names:Carla A.</infon><infon key="name_14">surname:Simmons;given-names:Shirley</infon><infon key="name_15">surname:Whittle;given-names:Jana S.</infon><infon key="name_16">surname:Weaver;given-names:Benjamin T.</infon><infon key="name_17">surname:Nesmith;given-names:Amy S.</infon><infon key="name_18">surname:Myers;given-names:Richard M.</infon><infon key="name_19">surname:Barsh;given-names:Gregory S.</infon><infon key="name_2">surname:Amaral;given-names:Michelle D.</infon><infon key="name_20">surname:Bebin;given-names:E. Martina</infon><infon key="name_21">surname:Cooper;given-names:Gregory M.</infon><infon key="name_22">surname:Cooper;given-names:Gregory M.</infon><infon key="name_23">surname:Cooper;given-names:Gregory M.</infon><infon key="name_3">surname:Finnila;given-names:Candice R.</infon><infon key="name_4">surname:Hiatt;given-names:Susan M.</infon><infon key="name_5">surname:Engel;given-names:Krysta L.</infon><infon key="name_6">surname:Cochran;given-names:J. Nicholas</infon><infon key="name_7">surname:Brothers;given-names:Kyle B.</infon><infon key="name_8">surname:East;given-names:Kelly M.</infon><infon key="name_9">surname:Gray;given-names:David E.</infon><infon key="section_type">TITLE</infon><infon key="title">Keywords</infon><infon key="type">front</infon><infon key="volume">9</infon><infon key="year">2017</infon><offset>0</offset><text>Genomic diagnosis for children with intellectual disability and/or developmental delay</text></passage><passage><infon key="section_type">ABSTRACT</infon><infon key="type">abstract_title_1</infon><offset>87</offset><text>Background</text></passage><passage><infon key="section_type">ABSTRACT</infon><infon key="type">abstract</infon><offset>98</offset><text>Developmental disabilities have diverse genetic causes that must be identified to facilitate precise diagnoses. We describe genomic data from 371 affected individuals, 309 of which were sequenced as proband-parent trios.</text></passage><passage><infon key="section_type">ABSTRACT</infon><infon key="type">abstract_title_1</infon><offset>319</offset><text>Methods</text></passage><passage><infon key="section_type">ABSTRACT</infon><infon key="type">abstract</infon><offset>327</offset><text>Whole-exome sequences (WES) were generated for 365 individuals (127 affected) and whole-genome sequences (WGS) were generated for 612 individuals (244 affected).</text></passage><passage><infon key="section_type">ABSTRACT</infon><infon key="type">abstract_title_1</infon><offset>489</offset><text>Results</text></passage><passage><infon key="section_type">ABSTRACT</infon><infon key="type">abstract</infon><offset>497</offset><text>Pathogenic or likely pathogenic variants were found in 100 individuals (27%), with variants of uncertain significance in an additional 42 (11.3%). We found that a family history of neurological disease, especially the presence of an affected first-degree relative, reduces the pathogenic/likely pathogenic variant identification rate, reflecting both the disease relevance and ease of interpretation of de novo variants. We also found that improvements to genetic knowledge facilitated interpretation changes in many cases. Through systematic reanalyses, we have thus far reclassified 15 variants, with 11.3% of families who initially were found to harbor a VUS and 4.7% of families with a negative result eventually found to harbor a pathogenic or likely pathogenic variant. To further such progress, the data described here are being shared through ClinVar, GeneMatcher, and dbGaP.</text></passage><passage><infon key="section_type">ABSTRACT</infon><infon key="type">abstract_title_1</infon><offset>1381</offset><text>Conclusions</text></passage><passage><infon key="section_type">ABSTRACT</infon><infon key="type">abstract</infon><offset>1393</offset><text>Our data strongly support the value of large-scale sequencing, especially WGS within proband-parent trios, as both an effective first-choice diagnostic tool and means to advance clinical and research progress related to pediatric neurological disease.</text></passage><passage><infon key="section_type">ABSTRACT</infon><infon key="type">abstract_title_1</infon><offset>1645</offset><text>Electronic supplementary material</text></passage><passage><infon key="section_type">ABSTRACT</infon><infon key="type">abstract</infon><offset>1679</offset><text>The online version of this article (doi:10.1186/s13073-017-0433-1) contains supplementary material, which is available to authorized users.</text></passage><passage><infon key="file">Tab3.xml</infon><infon key="id">Tab3</infon><infon key="section_type">TABLE</infon><infon key="type">table_caption</infon><offset>30344</offset><text>Variants with an increase in pathogenicity score due to reanalysis</text></passage><passage><infon key="file">Tab3.xml</infon><infon key="id">Tab3</infon><infon key="section_type">TABLE</infon><infon key="type">table</infon><infon key="xml">&lt;?xml version="1.0" encoding="UTF-8"?&gt;\\n&lt;table frame="hsides" rules="groups"&gt;&lt;thead&gt;&lt;tr&gt;&lt;th&gt;Gene&lt;/th&gt;&lt;th&gt;Affected individual ID(s)&lt;/th&gt;&lt;th&gt;Variant info&lt;/th&gt;&lt;th&gt;Original score&lt;/th&gt;&lt;th&gt;Updated score&lt;/th&gt;&lt;th&gt;Reason(s) for update&lt;/th&gt;&lt;th&gt;Evidence for upgrade&lt;/th&gt;&lt;/tr&gt;&lt;/thead&gt;&lt;tbody&gt;&lt;tr&gt;&lt;td&gt;DDX3X&lt;/td&gt;&lt;td&gt;00075-C&lt;/td&gt;&lt;td&gt;NM_001356.4(DDX3X):c.745G &amp;gt; T (p.Glu249Ter)&lt;/td&gt;&lt;td&gt;VUS&lt;/td&gt;&lt;td&gt;Pathogenic&lt;/td&gt;&lt;td&gt;Publication&lt;/td&gt;&lt;td&gt;&lt;xref ref-type="bibr" rid="CR38"&gt;38&lt;/xref&gt;&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;EBF3&lt;/td&gt;&lt;td&gt;00006-C&lt;/td&gt;&lt;td&gt;NM_001005463.2(EBF3):c.1101 + 1G &amp;gt; T&lt;/td&gt;&lt;td&gt;VUS&lt;/td&gt;&lt;td&gt;Pathogenic&lt;/td&gt;&lt;td&gt;GeneMatcher&lt;/td&gt;&lt;td&gt;Collaboration with several other groups identified patients with comparable genotypes and phenotypes &lt;xref ref-type="bibr" rid="CR37"&gt;37&lt;/xref&gt;&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;EBF3&lt;/td&gt;&lt;td&gt;00032-C&lt;/td&gt;&lt;td&gt;NM_001005463.2(EBF3):c.530C &amp;gt; T (p.Pro177Leu)&lt;/td&gt;&lt;td&gt;VUS&lt;/td&gt;&lt;td&gt;Pathogenic&lt;/td&gt;&lt;td&gt;GeneMatcher&lt;/td&gt;&lt;td&gt;Collaboration with several other groups identified patients with comparable genotypes and phenotypes &lt;xref ref-type="bibr" rid="CR37"&gt;37&lt;/xref&gt;&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;KIAA2022&lt;/td&gt;&lt;td&gt;00082-C&lt;/td&gt;&lt;td&gt;NM_001008537.2(KIAA2022):c.2999_3000delCT (p.Ser1000Cysfs)&lt;/td&gt;&lt;td&gt;VUS&lt;/td&gt;&lt;td&gt;Pathogenic&lt;/td&gt;&lt;td&gt;Publication/Personal communication&lt;/td&gt;&lt;td&gt;&lt;xref ref-type="bibr" rid="CR39"&gt;39&lt;/xref&gt;&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;TCF20&lt;/td&gt;&lt;td&gt;00078-C&lt;/td&gt;&lt;td&gt;NM_005650.3(TCF20):c.5385_5386delTG (p.Cys1795Trpfs)&lt;/td&gt;&lt;td&gt;VUS&lt;/td&gt;&lt;td&gt;Pathogenic&lt;/td&gt;&lt;td&gt;Publication&lt;/td&gt;&lt;td&gt;&lt;xref ref-type="bibr" rid="CR16"&gt;16&lt;/xref&gt;&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;ARID2&lt;/td&gt;&lt;td&gt;00026-C&lt;/td&gt;&lt;td&gt;NM_152641.2(ARID2):c.1708delT (p.Cys570Valfs)&lt;/td&gt;&lt;td&gt;NR&lt;/td&gt;&lt;td&gt;Pathogenic&lt;/td&gt;&lt;td&gt;Publication&lt;/td&gt;&lt;td&gt;&lt;xref ref-type="bibr" rid="CR40"&gt;40&lt;/xref&gt;&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;CDK13&lt;/td&gt;&lt;td&gt;00253-C&lt;/td&gt;&lt;td&gt;NM_003718.4(CDK13):c.2525A &amp;gt; G (p.Asn842Ser)&lt;/td&gt;&lt;td&gt;NR&lt;/td&gt;&lt;td&gt;Pathogenic&lt;/td&gt;&lt;td&gt;Publication&lt;/td&gt;&lt;td&gt;&lt;xref ref-type="bibr" rid="CR16"&gt;16&lt;/xref&gt;&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;CLPB&lt;/td&gt;&lt;td&gt;00127-C&lt;/td&gt;&lt;td&gt;NM_030813.5(CLPB):c.1222A &amp;gt; G (p.Arg408Gly) NM_030813.5(CLPB):c.1249C &amp;gt; T (p.Arg417Ter)&lt;/td&gt;&lt;td&gt;NR&lt;/td&gt;&lt;td&gt;Pathogenic&lt;/td&gt;&lt;td&gt;Publication&lt;/td&gt;&lt;td&gt;&lt;xref ref-type="bibr" rid="CR41"&gt;41&lt;/xref&gt;&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;FGF12&lt;/td&gt;&lt;td&gt;00074-C&lt;/td&gt;&lt;td&gt;NM_021032.4(FGF12):c.341G &amp;gt; A (p.R114H)&lt;/td&gt;&lt;td&gt;NR&lt;/td&gt;&lt;td&gt;Pathogenic&lt;/td&gt;&lt;td&gt;Publication&lt;/td&gt;&lt;td&gt;&lt;xref ref-type="bibr" rid="CR42"&gt;42&lt;/xref&gt;&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;MTOR&lt;/td&gt;&lt;td&gt;00040-C&lt;/td&gt;&lt;td&gt;NM_004958.3(MTOR):c.4785G &amp;gt; A (p.Met1595Ile)&lt;/td&gt;&lt;td&gt;NR&lt;/td&gt;&lt;td&gt;Pathogenic&lt;/td&gt;&lt;td&gt;Publication&lt;/td&gt;&lt;td&gt;For review&lt;xref ref-type="bibr" rid="CR26"&gt;26&lt;/xref&gt;; see also &lt;xref ref-type="bibr" rid="CR27"&gt;27&lt;/xref&gt;&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;MTOR&lt;/td&gt;&lt;td&gt;00028-C, 00028-C2&lt;/td&gt;&lt;td&gt;NM_004958.3(MTOR):c.5663 T &amp;gt; G (p.Phe1888Cys)&lt;/td&gt;&lt;td&gt;NR&lt;/td&gt;&lt;td&gt;Pathogenic&lt;/td&gt;&lt;td&gt;Filter&lt;/td&gt;&lt;td&gt;In original filter, required allele count of one; this variant was present in identical twins&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;HDAC8&lt;/td&gt;&lt;td&gt;00001-C&lt;/td&gt;&lt;td&gt;NM_018486.2(HDAC8):c.737 + 1G &amp;gt; A&lt;/td&gt;&lt;td&gt;NR&lt;/td&gt;&lt;td&gt;Likely pathogenic&lt;/td&gt;&lt;td&gt;Filter&lt;/td&gt;&lt;td&gt;In original filter, required depth for all members of trio was set to 10 reads; father had only 7&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;LAMA2&lt;/td&gt;&lt;td&gt;00055-C, 00055-S&lt;/td&gt;&lt;td&gt;NM_000426.3(LAMA2):c.715C &amp;gt; T (p.Arg239Cys)&lt;/td&gt;&lt;td&gt;NR&lt;/td&gt;&lt;td&gt;Likely pathogenic&lt;/td&gt;&lt;td&gt;Clarification of clinical phenotype&lt;/td&gt;&lt;td&gt;Discussion with clinicians was necessary to determine that patients\\\' phenotypes did match those observed for LAMA2&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;MAST1&lt;/td&gt;&lt;td&gt;00270-C&lt;/td&gt;&lt;td&gt;NM_014975.2:c.278C &amp;gt; T, p.Ser93Leu&lt;/td&gt;&lt;td&gt;NR&lt;/td&gt;&lt;td&gt;Likely pathogenic&lt;/td&gt;&lt;td&gt;GeneMatcher&lt;/td&gt;&lt;td&gt;Collaboration with several other groups identified patients with comparable genotypes and phenotypes&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;SUV420H1&lt;/td&gt;&lt;td&gt;00056-C&lt;/td&gt;&lt;td&gt;NM_017635.3:c.2497G &amp;gt; T, p.Glu833X&lt;/td&gt;&lt;td&gt;NR&lt;/td&gt;&lt;td&gt;Likely pathogenic&lt;/td&gt;&lt;td&gt;Publication&lt;/td&gt;&lt;td&gt;&lt;xref ref-type="bibr" rid="CR16"&gt;16&lt;/xref&gt;&lt;/td&gt;&lt;/tr&gt;&lt;/tbody&gt;&lt;/table&gt;\\n</infon><offset>30411</offset><text>Gene\\tAffected individual ID(s)\\tVariant info\\tOriginal score\\tUpdated score\\tReason(s) for update\\tEvidence for upgrade\\t \\tDDX3X\\t00075-C\\tNM_001356.4(DDX3X):c.745G &gt; T (p.Glu249Ter)\\tVUS\\tPathogenic\\tPublication\\t\\t \\tEBF3\\t00006-C\\tNM_001005463.2(EBF3):c.1101 + 1G &gt; T\\tVUS\\tPathogenic\\tGeneMatcher\\tCollaboration with several other groups identified patients with comparable genotypes and phenotypes \\t \\tEBF3\\t00032-C\\tNM_001005463.2(EBF3):c.530C &gt; T (p.Pro177Leu)\\tVUS\\tPathogenic\\tGeneMatcher\\tCollaboration with several other groups identified patients with comparable genotypes and phenotypes \\t \\tKIAA2022\\t00082-C\\tNM_001008537.2(KIAA2022):c.2999_3000delCT (p.Ser1000Cysfs)\\tVUS\\tPathogenic\\tPublication/Personal communication\\t\\t \\tTCF20\\t00078-C\\tNM_005650.3(TCF20):c.5385_5386delTG (p.Cys1795Trpfs)\\tVUS\\tPathogenic\\tPublication\\t\\t \\tARID2\\t00026-C\\tNM_152641.2(ARID2):c.1708delT (p.Cys570Valfs)\\tNR\\tPathogenic\\tPublication\\t\\t \\tCDK13\\t00253-C\\tNM_003718.4(CDK13):c.2525A &gt; G (p.Asn842Ser)\\tNR\\tPathogenic\\tPublication\\t\\t \\tCLPB\\t00127-C\\tNM_030813.5(CLPB):c.1222A &gt; G (p.Arg408Gly) NM_030813.5(CLPB):c.1249C &gt; T (p.Arg417Ter)\\tNR\\tPathogenic\\tPublication\\t\\t \\tFGF12\\t00074-C\\tNM_021032.4(FGF12):c.341G &gt; A (p.R114H)\\tNR\\tPathogenic\\tPublication\\t\\t \\tMTOR\\t00040-C\\tNM_004958.3(MTOR):c.4785G &gt; A (p.Met1595Ile)\\tNR\\tPathogenic\\tPublication\\tFor review; see also \\t \\tMTOR\\t00028-C, 00028-C2\\tNM_004958.3(MTOR):c.5663 T &gt; G (p.Phe1888Cys)\\tNR\\tPathogenic\\tFilter\\tIn original filter, required allele count of one; this variant was present in identical twins\\t \\tHDAC8\\t00001-C\\tNM_018486.2(HDAC8):c.737 + 1G &gt; A\\tNR\\tLikely pathogenic\\tFilter\\tIn original filter, required depth for all members of trio was set to 10 reads; father had only 7\\t \\tLAMA2\\t00055-C, 00055-S\\tNM_000426.3(LAMA2):c.715C &gt; T (p.Arg239Cys)\\tNR\\tLikely pathogenic\\tClarification of clinical phenotype\\tDiscussion with clinicians was necessary to determine that patients\\\' phenotypes did match those observed for LAMA2\\t \\tMAST1\\t00270-C\\tNM_014975.2:c.278C &gt; T, p.Ser93Leu\\tNR\\tLikely pathogenic\\tGeneMatcher\\tCollaboration with several other groups identified patients with comparable genotypes and phenotypes\\t \\tSUV420H1\\t00056-C\\tNM_017635.3:c.2497G &gt; T, p.Glu833X\\tNR\\tLikely pathogenic\\tPublication\\t\\t \\t</text></passage><passage><infon key="file">Tab3.xml</infon><infon key="id">Tab3</infon><infon key="section_type">TABLE</infon><infon key="type">table_foot</infon><offset>32651</offset><text>\\nC child/proband, C2 affected identical twin, S affected sibling, NR no returnables, VUS variant of uncertain significance</text></passage></document>\n',
        }
    )
    return paper


@pytest.fixture
def mock_llm_client(mock_client: Any) -> Any:
    return mock_client(OpenAIClient)


@pytest.fixture
def mock_factory(mock_client: Any) -> Any:
    return mock_client(HGVSVariantFactory)


@pytest.fixture
def mock_comparator(mock_client: Any) -> Any:
    return mock_client(HGVSVariantComparator)


def test_sanity_check_failure(
    paper: Paper, mock_llm_client: Any, mock_factory: Any, mock_comparator: Any
) -> None:
    # Remove the full text content for the paper.
    paper.fulltext_xml = ''

    # Paper fails sanity check.
    llm_client = mock_llm_client({'relevant': False})
    of = ObservationFinder(llm_client, mock_factory(None), mock_comparator({}))
    result = asyncio.run(of.find_observations('gene', paper))
    assert result == []

    # Paper passes sanity check, but only because json is unparsable.
    llm_client = mock_llm_client({}, {})
    of = ObservationFinder(llm_client, mock_factory(None), mock_comparator({}))
    # Paper has no full text, no observations should be found.
    result = asyncio.run(of.find_observations('gene', paper))
    assert result == []


def test_find_observations_no_variants(
    paper: Paper, mock_llm_client: Any, mock_factory: Any, mock_comparator: Any
) -> None:
    # Remove the full text content for the paper.
    paper.fulltext_xml = ''

    llm_client = mock_llm_client({'relevant': True}, {})
    of = ObservationFinder(llm_client, mock_factory(None), mock_comparator({}))
    result = asyncio.run(of.find_observations('gene', paper))
    assert result == []


def test_find_observations_single_variant(
    paper: Paper, mock_llm_client: Any, mock_factory: Any, mock_comparator: Any
) -> None:
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> prompt_json
        {
            'variants': ['c.530C > T']
        },  # _find_variant_descriptions -> prompt_json (main text)
        {'variants': []},  # _find_variant_descriptions -> prompt_json (table 1)
        {'related': True},  # _check_variant_gene_relationship -> prompt_json
        {'patients': ['proband']},  # _find_patients -> prompt_json (main text)
        {'patients': []},  # _find_patients -> prompt_json (table 1)
        {'proband': ['c.530C > T']},  # _link_entities -> prompt_json
    )
    variant = HGVSVariant(
        'c.530C>T', 'EBF3', 'NM_001005463.2', False, True, None, None, []
    )
    factory = mock_factory(variant)
    comparator = mock_comparator({variant: {variant}})
    of = ObservationFinder(llm_client, factory, comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert len(result) == 1
    assert result[0].variant == variant
    assert result[0].individual == 'proband'
    assert result[0].variant_descriptions == ['c.530C > T']
    assert result[0].patient_descriptions == ['proband']
    assert result[0].paper_id == 'pmid:28554332'


def test_find_observations_many_patients(
    paper: Paper, mock_llm_client: Any, mock_factory: Any, mock_comparator: Any
) -> None:
    # Cover most of the multi-patient edge cases.
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['c.530C > T']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
        {'related': True},  # _check_variant_gene_relationship -> _run_json_prompt
        {
            'patients': [
                'proband 1',
                'proband 2',
                'proband 3',
                'proband 4',
                'probands 5 and 6',
            ]
        },
        # ... _find_patients -> _run_json_prompt (main text)
        {'patients': ['unknown']},  # _find_patients -> _run_json_prompt (table 1)
        {'patients': ['proband 5', 'proband 6']},  # split_patient -> _run_json_prompt
        {'is_patient': True},  # _check_patients -> _run_json_prompt
        {'is_patient': True},  # _check_patients -> _run_json_prompt
        {'is_patient': True},  # _check_patients -> _run_json_prompt
        {'is_patient': True},  # _check_patients -> _run_json_prompt
        {'is_patient': True},  # _check_patients -> _run_json_prompt
        {'is_patient': False},  # _check_patients -> _run_json_prompt
        # Note, we're not guaranteed that the patient we filtered above is proband 6, but we can enforce it with the
        # next LLM call.
        {
            'proband 1': ['c.530C > T'],
            'proband 2': ['c.530C > T'],
            'proband 3': ['c.530C > T'],
            'proband 4': ['c.530C > T'],
            'proband 5': ['c.530C > T'],
        },  # _link_entities -> _run_json_prompt
    )
    variant = HGVSVariant(
        'c.530C > T', 'EBF3', 'NM_001005463.2', False, True, None, None, []
    )
    factory = mock_factory(variant)
    comparator = mock_comparator({variant: {variant}})
    of = ObservationFinder(llm_client, factory, comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert len(result) == 5

    for _, r in enumerate(result):
        # Don't test individual IDs because we don't have determinism about which patient was dropped (depends on
        # asyncio).
        assert r.variant == variant
        assert r.variant_descriptions == ['c.530C > T']
        assert r.paper_id == 'pmid:28554332'

    # Cover the full-text fallback multi-patient edge case.
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['c.530C > T']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
        {'related': True},  # _check_variant_gene_relationship -> _run_json_prompt
        {'patients': ['proband 1', 'proband 2', 'proband 3', 'proband 4', 'proband 5']},
        # ... _find_patients -> _run_json_prompt (main text)
        {'patients': []},  # _find_patients -> _run_json_prompt (table 1)
        {'is_patient': False},  # _check_patients -> _run_json_prompt
        {'is_patient': False},  # _check_patients -> _run_json_prompt
        {'is_patient': False},  # _check_patients -> _run_json_prompt
        {'is_patient': False},  # _check_patients -> _run_json_prompt
        {'is_patient': False},  # _check_patients -> _run_json_prompt
        {'is_patient': True},  # _check_patients -> _run_json_prompt
        {'is_patient': False},  # _check_patients -> _run_json_prompt
        {'is_patient': False},  # _check_patients -> _run_json_prompt
        {'is_patient': False},  # _check_patients -> _run_json_prompt
        {'is_patient': False},  # _check_patients -> _run_json_prompt
        # Note, we're not guaranteed that the patient we filtered above is individual 6, but we can enforce it with the
        # next LLM call.
        {'proband 1': ['c.530C > T']},  # _link_entities -> _run_json_prompt
    )
    variant = HGVSVariant(
        'c.530C > T', 'EBF3', 'NM_001005463.2', False, True, None, None, []
    )
    factory = mock_factory(variant)
    comparator = mock_comparator({variant: {variant}})
    of = ObservationFinder(llm_client, factory, comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert len(result) == 1
    assert result[0].variant == variant
    assert result[0].variant_descriptions == ['c.530C > T']
    assert result[0].paper_id == 'pmid:28554332'


def test_find_observations_numeric_patients(
    paper: Paper, mock_llm_client: Any, mock_factory: Any, mock_comparator: Any
) -> None:
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['c.530C > T']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
        {'related': True},  # _check_variant_gene_relationship -> _run_json_prompt
        {'patients': ['proband 21', '21']},
        # ... _find_patients -> _run_json_prompt (main text)
        {'patients': ['unknown']},  # _find_patients -> _run_json_prompt (table 1)
        # Note, we're not guaranteed that the patient we filtered above is proband 21, but we can enforce it with the
        # next LLM call.
        {'proband 21': ['c.530C > T']},  # _link_entities -> _run_json_prompt
    )
    variant = HGVSVariant(
        'c.530C > T', 'EBF3', 'NM_001005463.2', False, True, None, None, []
    )
    factory = mock_factory(variant)
    comparator = mock_comparator({variant: {variant}})
    of = ObservationFinder(llm_client, factory, comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert len(result) == 1
    assert result[0].variant == variant
    assert result[0].individual == 'proband 21'
    assert result[0].variant_descriptions == ['c.530C > T']
    assert result[0].patient_descriptions == ['proband 21']
    assert result[0].paper_id == 'pmid:28554332'


def test_find_observations_refseq_edge_cases(
    paper: Paper, mock_llm_client: Any, mock_factory: Any, mock_comparator: Any
) -> None:
    # Test variants with embedded refseqs.
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['NM_001005463.2:c.530C>T']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
        {'patients': ['proband']},  # _find_patients -> _run_json_prompt (main text)
        {'patients': []},  # _find_patients -> _run_json_prompt (table 1)
        {'proband': ['NM_001005463.2:c.530C>T']},  # _link_entities -> _run_json_prompt
    )
    variant = HGVSVariant(
        'c.530C>T', 'EBF3', 'NM_001005463.2', False, True, None, None, []
    )
    factory = mock_factory(variant)
    comparator = mock_comparator({variant: {variant}})
    of = ObservationFinder(llm_client, factory, comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert len(result) == 1
    assert result[0].variant == variant
    assert result[0].individual == 'proband'
    assert result[0].variant_descriptions == ['NM_001005463.2:c.530C>T']
    assert result[0].patient_descriptions == ['proband']
    assert result[0].paper_id == 'pmid:28554332'

    # Test bogus refseqs.
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['NZ_123456789.2:c.530C>T']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
    )

    of = ObservationFinder(llm_client, mock_factory(None), mock_comparator({}))
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert result == []


def test_find_observations_variant_edge_cases(
    paper: Paper, mock_llm_client: Any, mock_factory: Any, mock_comparator: Any
) -> None:
    # Test variants accidentally picked up from the example text.
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['c.530C > T', '1234A>T']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
        {'related': True},  # _check_variant_gene_relationship -> _run_json_prompt
        {'patients': ['proband']},  # _find_patients -> _run_json_prompt (main text)
        {'patients': []},  # _find_patients -> _run_json_prompt (table 1)
        {'proband': ['c.530C > T']},  # _link_entities -> _run_json_prompt
    )
    variant = HGVSVariant(
        'c.530C>T', 'EBF3', 'NM_001005463.2', False, True, None, None, []
    )
    factory = mock_factory(variant)
    comparator = mock_comparator({variant: {variant}})
    of = ObservationFinder(llm_client, factory, comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert len(result) == 1
    assert result[0].variant == variant
    assert result[0].individual == 'proband'
    assert result[0].variant_descriptions == ['c.530C > T']
    assert result[0].patient_descriptions == ['proband']
    assert result[0].paper_id == 'pmid:28554332'

    # Test variants with embedded gene names.
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['gEBF3(c.530C > T)']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
        {'patients': ['proband']},  # _find_patients -> _run_json_prompt (main text)
        {'patients': []},  # _find_patients -> _run_json_prompt (table 1)
        {'proband': ['gEBF3(c.530C > T)']},  # _link_entities -> _run_json_prompt
    )
    variant = HGVSVariant(
        'c.530C>T', 'EBF3', 'NM_001005463.2', False, True, None, None, []
    )
    factory = mock_factory(variant)
    comparator = mock_comparator({variant: {variant}})
    of = ObservationFinder(llm_client, factory, comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert len(result) == 1
    assert result[0].variant == variant
    assert result[0].individual == 'proband'
    assert result[0].variant_descriptions == ['gEBF3(c.530C > T)']
    assert result[0].patient_descriptions == ['proband']
    assert result[0].paper_id == 'pmid:28554332'

    # Test bogus variants.
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['123456789']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
    )

    of = ObservationFinder(llm_client, mock_factory(None), mock_comparator({}))
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert result == []

    # Test variants that fail creation.
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['c.530C>T']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
    )

    class FailingMockFactory(HGVSVariantFactory):
        def __init__(self):
            pass

        def parse(
            self, text_desc: str, gene_symbol: str | None, refseq: str | None = None
        ) -> HGVSVariant:
            raise ValueError('Unable to parse variant')

        def parse_rsid(self, hgvs: str) -> HGVSVariant:
            raise NotImplementedError()

    of = ObservationFinder(llm_client, FailingMockFactory(), mock_comparator({}))
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert result == []

    # Test unrelated variants
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['c.530C > T']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
        {'related': False},  # _check_variant_gene_relationship -> _run_json_prompt
    )
    variant = HGVSVariant(
        'c.530C>T', 'EBF3', 'NM_001005463.2', False, True, None, None, []
    )
    factory = mock_factory(variant)
    comparator = mock_comparator({variant: {variant}})
    of = ObservationFinder(llm_client, factory, comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert result == []


def test_find_observations_c_dot_variant(
    paper: Paper, mock_llm_client: Any, mock_factory: Any, mock_comparator: Any
) -> None:
    # Test variants with a gene gene-prefix.
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['EBF3:c.530C > T']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
        {'related': True},  # _check_variant_gene_relationship -> _run_json_prompt
        {'patients': ['proband']},  # _find_patients -> _run_json_prompt (main text)
        {'patients': []},  # _find_patients -> _run_json_prompt (table 1)
        {'proband': ['c.530C > T']},  # _link_entities -> _run_json_prompt
    )
    variant = HGVSVariant(
        'c.530C>T', 'EBF3', 'NM_001005463.2', False, True, None, None, []
    )
    factory = mock_factory(variant)
    comparator = mock_comparator({variant: {variant}})
    of = ObservationFinder(llm_client, factory, comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert len(result) == 1
    assert result[0].variant == variant
    assert result[0].individual == 'proband'
    assert result[0].variant_descriptions == ['c.530C > T']
    assert result[0].patient_descriptions == ['proband']
    assert result[0].paper_id == 'pmid:28554332'

    # Test variants missing c. prefix (SNP)
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['530C>T']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
        {'patients': ['proband']},  # _find_patients -> _run_json_prompt (main text)
        {'patients': []},  # _find_patients -> _run_json_prompt (table 1)
        {'proband': ['530C>T']},  # _link_entities -> _run_json_prompt
    )
    variant = HGVSVariant(
        'c.530C>T', 'EBF3', 'NM_001005463.2', False, True, None, None, []
    )
    factory = mock_factory(variant)
    comparator = mock_comparator({variant: {variant}})
    of = ObservationFinder(llm_client, factory, comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert len(result) == 1
    assert result[0].variant == variant
    assert result[0].individual == 'proband'
    assert result[0].variant_descriptions == ['530C>T']
    assert result[0].patient_descriptions == ['proband']
    assert result[0].paper_id == 'pmid:28554332'

    # Test variants missing c. prefix (del)
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['530delC']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
        {'patients': ['proband']},  # _find_patients -> _run_json_prompt (main text)
        {'patients': []},  # _find_patients -> _run_json_prompt (table 1)
        {'proband': ['530delC']},  # _link_entities -> _run_json_prompt
    )
    variant = HGVSVariant(
        'c.530delC', 'EBF3', 'NM_001005463.2', False, True, None, None, []
    )
    factory = mock_factory(variant)
    comparator = mock_comparator({variant: {variant}})
    of = ObservationFinder(llm_client, factory, comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert len(result) == 1
    assert result[0].variant == variant
    assert result[0].individual == 'proband'
    assert result[0].variant_descriptions == ['530delC']
    assert result[0].patient_descriptions == ['proband']
    assert result[0].paper_id == 'pmid:28554332'

    # Test variants missing c. prefix (ins)
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['530insT']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
        {'patients': ['proband']},  # _find_patients -> _run_json_prompt (main text)
        {'patients': []},  # _find_patients -> _run_json_prompt (table 1)
        {'proband': ['530insT']},  # _link_entities -> _run_json_prompt
    )
    variant = HGVSVariant(
        'c.530insT', 'EBF3', 'NM_001005463.2', False, True, None, None, []
    )
    factory = mock_factory(variant)
    comparator = mock_comparator({variant: {variant}})
    of = ObservationFinder(llm_client, factory, comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert len(result) == 1
    assert result[0].variant == variant
    assert result[0].individual == 'proband'
    assert result[0].variant_descriptions == ['530insT']
    assert result[0].patient_descriptions == ['proband']
    assert result[0].paper_id == 'pmid:28554332'


def test_find_observations_p_dot_variant(
    paper: Paper, mock_llm_client: Any, mock_factory: Any, mock_comparator: Any
) -> None:
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['p.Pro177Leu']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
        {'related': True},  # _check_variant_gene_relationship -> _run_json_prompt
        {'patients': ['proband']},  # _find_patients -> _run_json_prompt (main text)
        {'patients': []},  # _find_patients -> _run_json_prompt (table 1)
        {'proband': ['p.Pro177Leu']},  # _link_entities -> _run_json_prompt
    )
    variant = HGVSVariant(
        'p.Pro177Leu', 'EBF3', 'NP_123456.2', False, True, None, None, []
    )
    factory = mock_factory(variant)
    comparator = mock_comparator({variant: {variant}})
    of = ObservationFinder(llm_client, factory, comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert len(result) == 1
    assert result[0].variant == variant
    assert result[0].individual == 'proband'
    assert result[0].variant_descriptions == ['p.Pro177Leu']
    assert result[0].patient_descriptions == ['proband']
    assert result[0].paper_id == 'pmid:28554332'

    # Test cases where p. is missing
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['NP_123456.2:P177L']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
        {'patients': ['proband']},  # _find_patients -> _run_json_prompt (main text)
        {'patients': []},  # _find_patients -> _run_json_prompt (table 1)
        {'proband': ['NP_123456.2:P177L']},  # _link_entities -> _run_json_prompt
    )
    variant = HGVSVariant('p.P177L', 'EBF3', 'NP_123456.2', False, True, None, None, [])
    factory = mock_factory(variant)
    comparator = mock_comparator({variant: {variant}})
    of = ObservationFinder(llm_client, factory, comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert len(result) == 1
    assert result[0].variant == variant
    assert result[0].individual == 'proband'
    assert result[0].variant_descriptions == ['NP_123456.2:P177L']
    assert result[0].patient_descriptions == ['proband']
    assert result[0].paper_id == 'pmid:28554332'

    # Test extra framshift info
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['NP_123456.2:P177fsLQQX']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
        {'patients': ['proband']},  # _find_patients -> _run_json_prompt (main text)
        {'patients': []},  # _find_patients -> _run_json_prompt (table 1)
        {'proband': ['NP_123456.2:P177fsLQQX']},  # _link_entities -> _run_json_prompt
    )
    variant = HGVSVariant(
        'p.P177fs', 'EBF3', 'NP_123456.2', False, True, None, None, []
    )
    factory = mock_factory(variant)
    comparator = mock_comparator({variant: {variant}})
    of = ObservationFinder(llm_client, factory, comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert len(result) == 1
    assert result[0].variant == variant
    assert result[0].individual == 'proband'
    assert result[0].variant_descriptions == ['NP_123456.2:P177fsLQQX']
    assert result[0].patient_descriptions == ['proband']
    assert result[0].paper_id == 'pmid:28554332'


def test_find_observations_g_dot_variant(
    paper: Paper, mock_llm_client: Any, mock_factory: Any, mock_comparator: Any
) -> None:
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['chr1:g.8675309A>T']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
        {'genome_build': 'GRCh38'},  # _find_genome_build -> _run_json_prompt
        {'related': True},  # _check_variant_gene_relationship -> _run_json_prompt
        {'patients': ['proband']},  # _find_patients -> _run_json_prompt (main text)
        {'patients': []},  # _find_patients -> _run_json_prompt (table 1)
        {'proband': ['chr1:g.8675309A>T']},  # _link_entities -> _run_json_prompt
    )

    # By using an invalid variant we're requiring _check_variant_gene_relationship to evaluate even though there's no
    # text mentioning this variant in the source paper.
    variant = HGVSVariant(
        'g.8675309A>T', 'EBF3', 'GRCh38(chr1)', False, False, None, None, []
    )
    factory = mock_factory(variant)
    comparator = mock_comparator({variant: {variant}})
    of = ObservationFinder(llm_client, factory, comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert len(result) == 1
    assert result[0].variant == variant
    assert result[0].individual == 'proband'
    assert result[0].variant_descriptions == ['chr1:g.8675309A>T']
    assert result[0].patient_descriptions == ['proband']
    assert result[0].paper_id == 'pmid:28554332'


def test_find_observations_rsid_variant(
    paper: Paper, mock_llm_client: Any, mock_factory: Any, mock_comparator: Any
) -> None:
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['rs8675309', 'rs9035768']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
        {'related': True},  # _check_variant_gene_relationship -> _run_json_prompt
        {'patients': ['proband']},  # _find_patients -> _run_json_prompt (main text)
        {'patients': []},  # _find_patients -> _run_json_prompt (table 1)
        {'proband': ['rs8675309']},  # _link_entities -> _run_json_prompt
    )

    # By using an invalid variant we're requiring _check_variant_gene_relationship to evaluate even though there's no
    # text mentioning this variant in the source paper.
    variant1 = HGVSVariant(
        'c.5555A>G', 'EBF3', 'NM_001005463.2', False, False, None, None, []
    )
    variant2 = HGVSVariant(
        'c.1919A>G', 'BRCA2', 'NM_123456.7', False, False, None, None, []
    )

    class DeterministicMockFactory(HGVSVariantFactory):
        def __init__(self):
            pass

        def parse(
            self, text_desc: str, gene_symbol: str | None, refseq: str | None = None
        ) -> HGVSVariant:
            raise NotImplementedError()

        def parse_rsid(self, hgvs: str) -> HGVSVariant:
            if hgvs == 'rs8675309':
                return variant1
            if hgvs == 'rs9035768':
                return variant2
            raise ValueError(f'Unexpected variant {hgvs}')

    comparator = mock_comparator({variant1: {variant1}})
    of = ObservationFinder(llm_client, DeterministicMockFactory(), comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert len(result) == 1
    assert result[0].variant == variant1
    assert result[0].individual == 'proband'
    assert result[0].variant_descriptions == ['rs8675309']
    assert result[0].patient_descriptions == ['proband']
    assert result[0].paper_id == 'pmid:28554332'

    # Test the case where the variant factory can't create a variant given an rsid.

    class FailingMockFactory(HGVSVariantFactory):
        def __init__(self):
            pass

        def parse(
            self, text_desc: str, gene_symbol: str | None, refseq: str | None = None
        ) -> HGVSVariant:
            raise NotImplementedError()

        def parse_rsid(self, hgvs: str) -> HGVSVariant:
            raise ValueError('Unable to parse variant')

    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['rs8675309']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
    )

    of = ObservationFinder(llm_client, FailingMockFactory(), mock_comparator({}))
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert result == []


def test_find_observations_associated_variants(
    paper: Paper, mock_llm_client: Any, mock_factory: Any, mock_comparator: Any
) -> None:
    # Test variants with a gene gene-prefix.
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['c.530C > T (p.Pro177Leu)']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
        {
            'variants': ['c.530C > T', 'p.Pro177Leu']
        },  # split variants -> run_json_prompt
        {'related': True},  # _check_variant_gene_relationship -> _run_json_prompt
        {'patients': ['proband']},  # _find_patients -> _run_json_prompt (main text)
        {'patients': []},  # _find_patients -> _run_json_prompt (table 1)
        {'proband': ['c.530C > T']},  # _link_entities -> _run_json_prompt
    )
    variant1 = HGVSVariant(
        'c.530C>T', 'EBF3', 'NM_001005463.2', False, True, None, None, []
    )
    variant2 = HGVSVariant(
        'p.Pro177Leu', 'EBF3', 'NP_123456.2', False, True, None, None, []
    )
    factory = mock_factory(variant1, variant2)
    comparator = mock_comparator({variant1: {variant1, variant2}})
    of = ObservationFinder(llm_client, factory, comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert len(result) == 1
    assert result[0].variant == variant1
    assert result[0].individual == 'proband'
    assert result[0].variant_descriptions == ['c.530C > T']
    assert result[0].patient_descriptions == ['proband']
    assert result[0].paper_id == 'pmid:28554332'


def test_find_observations_linking_edge_cases(
    paper: Paper, mock_llm_client: Any, mock_factory: Any, mock_comparator: Any
) -> None:
    # Test variants with unknown possessor.
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['c.530C>T', 'c.540G>A']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
        {'patients': ['proband']},  # _find_patients -> _run_json_prompt (main text)
        {'patients': []},  # _find_patients -> _run_json_prompt (table 1)
        {
            'proband': ['c.530C>T'],
            'unmatched_variants': ['c.540G>A'],
        },  # _link_entities -> _run_json_prompt
    )

    class DeterministicMockFactory(HGVSVariantFactory):
        def __init__(self):
            pass

        def parse(
            self, text_desc: str, gene_symbol: str | None, refseq: str | None = None
        ) -> HGVSVariant:
            if text_desc == 'c.530C>T':
                return HGVSVariant(
                    'c.530C>T', 'EBF3', 'NM_001005463.2', False, True, None, None, []
                )
            if text_desc == 'c.540G>A':
                return HGVSVariant(
                    'c.540G>A', 'EBF3', 'NM_001005463.2', False, True, None, None, []
                )
            raise ValueError(f'Unexpected variant {text_desc}')

        def parse_rsid(self, hgvs: str) -> HGVSVariant:
            raise NotImplementedError()

    variant1 = HGVSVariant(
        'c.530C>T', 'EBF3', 'NM_001005463.2', False, True, None, None, []
    )
    variant2 = HGVSVariant(
        'c.540G>A', 'EBF3', 'NM_001005463.2', False, True, None, None, []
    )
    comparator = mock_comparator({variant1: {variant1}, variant2: {variant2}})
    of = ObservationFinder(llm_client, DeterministicMockFactory(), comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert len(result) == 2
    assert result[0].variant == variant1
    assert result[0].individual == 'proband'
    assert result[0].variant_descriptions == ['c.530C>T']
    assert result[0].patient_descriptions == ['proband']
    assert result[0].paper_id == 'pmid:28554332'
    assert result[1].variant == variant2
    assert result[1].individual == 'unknown'
    assert result[1].variant_descriptions == ['c.540G>A']
    assert result[1].patient_descriptions == ['unknown']
    assert result[1].paper_id == 'pmid:28554332'

    # Test extra variants with unknown possessor.
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['c.530C>T']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
        {'patients': ['proband']},  # _find_patients -> _run_json_prompt (main text)
        {'patients': []},  # _find_patients -> _run_json_prompt (table 1)
        {
            'proband': ['c.540G>A'],
            'unmatched_variants': ['c.530C>T'],
        },  # _link_entities -> _run_json_prompt
    )

    # Reuse DeterministicMockFactory from above.
    variant1 = HGVSVariant(
        'c.530C>T', 'EBF3', 'NM_001005463.2', False, True, None, None, []
    )
    variant2 = HGVSVariant(
        'c.540G>A', 'EBF3', 'NM_001005463.2', False, True, None, None, []
    )
    comparator = mock_comparator({variant1: {variant1}, variant2: {variant2}})
    of = ObservationFinder(llm_client, DeterministicMockFactory(), comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert len(result) == 1
    assert result[0].variant == variant1
    assert result[0].individual == 'unknown'
    assert result[0].variant_descriptions == ['c.530C>T']
    assert result[0].patient_descriptions == ['unknown']
    assert result[0].paper_id == 'pmid:28554332'

    # Test duplicate observations.
    llm_client = mock_llm_client(
        {'relevant': True},  # _sanity_check_paper -> _run_json_prompt
        {
            'variants': ['c.530C>T']
        },  # _find_variant_descriptions -> _run_json_prompt (main text)
        {'variants': []},  # _find_variant_descriptions -> _run_json_prompt (table 1)
        {'patients': ['proband']},  # _find_patients -> _run_json_prompt (main text)
        {'patients': []},  # _find_patients -> _run_json_prompt (table 1)
        {
            'proband': ['c.530C>T'],
            'unmatched_variants': ['c.530C>T'],
        },  # _link_entities -> _run_json_prompt
    )

    # Reuse DeterministicMockFactory from above.
    variant = HGVSVariant(
        'c.530C>T', 'EBF3', 'NM_001005463.2', False, True, None, None, []
    )
    comparator = mock_comparator({variant: {variant}})
    factory = mock_factory(variant)
    of = ObservationFinder(llm_client, factory, comparator)
    result = asyncio.run(of.find_observations('EBF3', paper))

    assert len(result) == 1
    assert result[0].variant == variant
    assert result[0].individual == 'proband'
    assert result[0].variant_descriptions == ['c.530C>T']
    assert result[0].patient_descriptions == ['proband']
    assert result[0].paper_id == 'pmid:28554332'
