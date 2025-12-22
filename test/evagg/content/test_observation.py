import asyncio
from typing import Any

import pytest

from lib.evagg.content import HGVSVariantComparator, ObservationFinder
from lib.evagg.content.variant import HGVSVariantFactory
from lib.evagg.llm import OpenAIClient
from lib.evagg.types import HGVSVariant, Paper


@pytest.fixture
def paper(monkeypatch) -> Paper:
    monkeypatch.setattr(
        Paper,
        'fulltext_md',
        property(
            lambda self: """
            Developmental disabilities have diverse genetic causes that must be identified to facilitate precise diagnoses. We describe genomic data from 371 affected individuals, 309 of which were sequenced as proband-parent trios.
            Whole-exome sequences (WES) were generated for 365 individuals (127 affected) and whole-genome sequences (WGS) were generated for 612 individuals (244 affected).
            Pathogenic or likely pathogenic variants were found in 100 individuals (27%), with variants of uncertain significance in an additional 42 (11.3%). We found that a family history of neurological disease, especially the presence of an affected first-degree relative, reduces the pathogenic/likely pathogenic variant identification rate, reflecting both the disease relevance and ease of interpretation of de novo variants. We also found that improvements to genetic knowledge facilitated interpretation changes in many cases. Through systematic reanalyses, we have thus far reclassified 15 variants, with 11.3% of families who initially were found to harbor a VUS and 4.7% of families with a negative result eventually found to harbor a pathogenic or likely pathogenic variant. To further such progress, the data described here are being shared through ClinVar, GeneMatcher, and dbGaP.
            Our data strongly support the value of large-scale sequencing, especially WGS within proband-parent trios, as both an effective first-choice diagnostic tool and means to advance clinical and research progress related to pediatric neurological disease.
            Electronic supplementary material
            The online version of this article (doi:10.1186/s13073-017-0433-1) contains supplementary material, which is available to authorized users.
            Variants with an increase in pathogenicity score due to reanalysis
            | Gene | Affected individual ID(s) | Variant info | Original score | Updated score | Reason(s) for update | Evidence for upgrade |
            |---|---|---|---|---|---|---|
            | DDX3X | 00075-C | NM_001356.4(DDX3X):c.745G > T (p.Glu249Ter) | VUS | Pathogenic | Publication | [38] |
            | EBF3 | 00006-C | NM_001005463.2(EBF3):c.1101+1G > T | VUS | Pathogenic | GeneMatcher | Collaboration with several other groups identified patients with comparable genotypes and phenotypes [37] |
            | EBF3 | 00032-C | NM_001005463.2(EBF3):c.530C > T (p.Pro177Leu) | VUS | Pathogenic | GeneMatcher | Collaboration with several other groups identified patients with comparable genotypes and phenotypes [37] |
            | KIAA2022 | 00082-C | NM_001008537.2(KIAA2022):c.2999_3000delCT (p.Ser1000Cysfs) | VUS | Pathogenic | Publication / Personal communication | [39] |
            | TCF20 | 00078-C | NM_005650.3(TCF20):c.5385_5386delTG (p.Cys1795Trpfs) | VUS | Pathogenic | Publication | [16] |
            | ARID2 | 00026-C | NM_152641.2(ARID2):c.1708delT (p.Cys570Valfs) | NR | Pathogenic | Publication | [40] |
            | CDK13 | 00253-C | NM_003718.4(CDK13):c.2525A > G (p.Asn842Ser) | NR | Pathogenic | Publication | [16] |
            | CLPB | 00127-C | NM_030813.5(CLPB):c.1222A > G (p.Arg408Gly); c.1249C > T (p.Arg417Ter) | NR | Pathogenic | Publication | [41] |
            | FGF12 | 00074-C | NM_021032.4(FGF12):c.341G > A (p.Arg114His) | NR | Pathogenic | Publication | [42] |
            | MTOR | 00040-C | NM_004958.3(MTOR):c.4785G > A (p.Met1595Ile) | NR | Pathogenic | Publication | For review [26]; see also [27] |
            | MTOR | 00028-C, 00028-C2 | NM_004958.3(MTOR):c.5663T > G (p.Phe1888Cys) | NR | Pathogenic | Filter | In original filter, required allele count of one; this variant was present in identical twins |
            | HDAC8 | 00001-C | NM_018486.2(HDAC8):c.737+1G > A | NR | Likely pathogenic | Filter | In original filter, required depth for all members of trio was set to 10 reads; father had only 7 |
            | LAMA2 | 00055-C, 00055-S | NM_000426.3(LAMA2):c.715C > T (p.Arg239Cys) | NR | Likely pathogenic | Clarification of clinical phenotype | Discussion with clinicians was necessary to determine that patients’ phenotypes matched those observed for LAMA2 |
            | MAST1 | 00270-C | NM_014975.2(MAST1):c.278C > T (p.Ser93Leu) | NR | Likely pathogenic | GeneMatcher | Collaboration with several other groups identified patients with comparable genotypes and phenotypes |
            | SUV420H1 | 00056-C | NM_017635.3(SUV420H1):c.2497G > T (p.Glu833Ter) | NR | Likely pathogenic | Publication | [16] |

        """
        ),
    )
    monkeypatch.setattr(
        Paper,
        'tables_md',
        property(
            lambda self: [
                """
            Variants with an increase in pathogenicity score due to reanalysis
            | Gene | Affected individual ID(s) | Variant info | Original score | Updated score | Reason(s) for update | Evidence for upgrade |
            |---|---|---|---|---|---|---|
            | DDX3X | 00075-C | NM_001356.4(DDX3X):c.745G > T (p.Glu249Ter) | VUS | Pathogenic | Publication | [38] |
            | EBF3 | 00006-C | NM_001005463.2(EBF3):c.1101+1G > T | VUS | Pathogenic | GeneMatcher | Collaboration with several other groups identified patients with comparable genotypes and phenotypes [37] |
            | EBF3 | 00032-C | NM_001005463.2(EBF3):c.530C > T (p.Pro177Leu) | VUS | Pathogenic | GeneMatcher | Collaboration with several other groups identified patients with comparable genotypes and phenotypes [37] |
            | KIAA2022 | 00082-C | NM_001008537.2(KIAA2022):c.2999_3000delCT (p.Ser1000Cysfs) | VUS | Pathogenic | Publication / Personal communication | [39] |
            | TCF20 | 00078-C | NM_005650.3(TCF20):c.5385_5386delTG (p.Cys1795Trpfs) | VUS | Pathogenic | Publication | [16] |
            | ARID2 | 00026-C | NM_152641.2(ARID2):c.1708delT (p.Cys570Valfs) | NR | Pathogenic | Publication | [40] |
            | CDK13 | 00253-C | NM_003718.4(CDK13):c.2525A > G (p.Asn842Ser) | NR | Pathogenic | Publication | [16] |
            | CLPB | 00127-C | NM_030813.5(CLPB):c.1222A > G (p.Arg408Gly); c.1249C > T (p.Arg417Ter) | NR | Pathogenic | Publication | [41] |
            | FGF12 | 00074-C | NM_021032.4(FGF12):c.341G > A (p.Arg114His) | NR | Pathogenic | Publication | [42] |
            | MTOR | 00040-C | NM_004958.3(MTOR):c.4785G > A (p.Met1595Ile) | NR | Pathogenic | Publication | For review [26]; see also [27] |
            | MTOR | 00028-C, 00028-C2 | NM_004958.3(MTOR):c.5663T > G (p.Phe1888Cys) | NR | Pathogenic | Filter | In original filter, required allele count of one; this variant was present in identical twins |
            | HDAC8 | 00001-C | NM_018486.2(HDAC8):c.737+1G > A | NR | Likely pathogenic | Filter | In original filter, required depth for all members of trio was set to 10 reads; father had only 7 |
            | LAMA2 | 00055-C, 00055-S | NM_000426.3(LAMA2):c.715C > T (p.Arg239Cys) | NR | Likely pathogenic | Clarification of clinical phenotype | Discussion with clinicians was necessary to determine that patients’ phenotypes matched those observed for LAMA2 |
            | MAST1 | 00270-C | NM_014975.2(MAST1):c.278C > T (p.Ser93Leu) | NR | Likely pathogenic | GeneMatcher | Collaboration with several other groups identified patients with comparable genotypes and phenotypes |
            | SUV420H1 | 00056-C | NM_017635.3(SUV420H1):c.2497G > T (p.Glu833Ter) | NR | Likely pathogenic | Publication | [16] |

            """,
            ]
        ),
    )
    monkeypatch.setattr(
        Paper,
        'sections_md',
        property(
            lambda self: [
                'Developmental disabilities have diverse genetic causes that must be identified to facilitate precise diagnoses. We describe genomic data from 371 affected individuals, 309 of which were sequenced as proband-parent trios.',
                'Whole-exome sequences (WES) were generated for 365 individuals (127 affected) and whole-genome sequences (WGS) were generated for 612 individuals (244 affected).',
                'Pathogenic or likely pathogenic variants were found in 100 individuals (27%), with variants of uncertain significance in an additional 42 (11.3%). We found that a family history of neurological disease, especially the presence of an affected first-degree relative, reduces the pathogenic/likely pathogenic variant identification rate, reflecting both the disease relevance and ease of interpretation of de novo variants. We also found that improvements to genetic knowledge facilitated interpretation changes in many cases. Through systematic reanalyses, we have thus far reclassified 15 variants, with 11.3% of families who initially were found to harbor a VUS and 4.7% of families with a negative result eventually found to harbor a pathogenic or likely pathogenic variant. To further such progress, the data described here are being shared through ClinVar, GeneMatcher, and dbGaP.',
                'Our data strongly support the value of large-scale sequencing, especially WGS within proband-parent trios, as both an effective first-choice diagnostic tool and means to advance clinical and research progress related to pediatric neurological disease.',
                'Electronic supplementary material',
                'The online version of this article (doi:10.1186/s13073-017-0433-1) contains supplementary material, which is available to authorized users.',
            ]
        ),
    )
    return Paper(
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
        }
    )


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
    paper: Paper,
    mock_llm_client: Any,
    mock_factory: Any,
    mock_comparator: Any,
    monkeypatch,
) -> None:
    # Remove the full content of the paper
    monkeypatch.setattr(
        Paper,
        'fulltext_md',
        property(lambda self: ''),
    )
    monkeypatch.setattr(
        Paper,
        'tables_md',
        property(lambda self: []),
    )

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
    paper: Paper,
    mock_llm_client: Any,
    mock_factory: Any,
    mock_comparator: Any,
    monkeypatch,
) -> None:
    # Remove the full content of the paper
    monkeypatch.setattr(
        Paper,
        'fulltext_md',
        property(lambda self: ''),
    )
    monkeypatch.setattr(
        Paper,
        'tables_md',
        property(lambda self: []),
    )

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
    assert result[0].paper.id == 'pmid:28554332'


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
        assert r.paper.id == 'pmid:28554332'

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
    assert result[0].paper.id == 'pmid:28554332'


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
    assert result[0].paper.id == 'pmid:28554332'


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
    assert result[0].paper.id == 'pmid:28554332'

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
    assert result[0].paper.id == 'pmid:28554332'

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
    assert result[0].paper.id == 'pmid:28554332'

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
    assert result[0].paper.id == 'pmid:28554332'

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
    assert result[0].paper.id == 'pmid:28554332'

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
    assert result[0].paper.id == 'pmid:28554332'

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
    assert result[0].paper.id == 'pmid:28554332'


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
    assert result[0].paper.id == 'pmid:28554332'

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
    assert result[0].paper.id == 'pmid:28554332'

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
    assert result[0].paper.id == 'pmid:28554332'


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
    assert result[0].paper.id == 'pmid:28554332'


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
    assert result[0].paper.id == 'pmid:28554332'

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
    assert result[0].paper.id == 'pmid:28554332'


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
    assert result[0].paper.id == 'pmid:28554332'
    assert result[1].variant == variant2
    assert result[1].individual == 'unknown'
    assert result[1].variant_descriptions == ['c.540G>A']
    assert result[1].patient_descriptions == ['unknown']
    assert result[1].paper.id == 'pmid:28554332'

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
    assert result[0].paper.id == 'pmid:28554332'

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
    assert result[0].paper.id == 'pmid:28554332'
