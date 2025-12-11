from typing import Any

import pytest

from lib.evagg import PromptBasedContentExtractor
from lib.evagg.content import (
    ObservationFinder,
    Observation,
    TextSection,
)
from lib.evagg.content.fulltext import get_fulltext
from lib.evagg.llm import OpenAIClient
from lib.evagg.ref import PyHPOClient, WebHPOClient
from lib.evagg.types import HGVSVariant, Paper


@pytest.fixture
def mock_prompt(mock_client: type) -> OpenAIClient:
    return mock_client(OpenAIClient)


@pytest.fixture
def mock_observation(mock_client: type) -> ObservationFinder:
    return mock_client(ObservationFinder)


@pytest.fixture
def mock_phenotype_fetcher(mock_client: type) -> PyHPOClient:
    return mock_client(PyHPOClient)


@pytest.fixture
def mock_phenotype_searcher(mock_client: type) -> WebHPOClient:
    return mock_client(WebHPOClient)


@pytest.fixture
def paper() -> Paper:
    return Paper(
        id='12345678',
        pmid='12345678',
        citation='Doe, J. et al. Test Journal 2021',
        title='Test Paper Title',
        abstract='This the abstract from a test paper.',
        pmcid='PMC123',
        can_access=True,
    )


def test_prompt_based_content_extractor_valid_fields(
    paper: Paper,
    mock_prompt: Any,
    mock_observation: Any,
    mock_phenotype_searcher: Any,
    mock_phenotype_fetcher: Any,
) -> None:
    fields = {
        'evidence_id': '12345678_c.1234A-G_unknown',  # TODO
        'gene': 'CHI3L1',
        'paper_id': '12345678',
        'citation': paper.props['citation'],
        'link': f'https://www.ncbi.nlm.nih.gov/pmc/articles/{paper.props["pmcid"]}',
        'paper_title': paper.props['title'],
        'hgvs_c': 'c.1234A>G',
        'hgvs_p': 'NA',
        'paper_variant': 'c.1234A>G',
        'transcript': 'transcript',
        'valid': 'True',
        'validation_error': 'not an error',
        'individual_id': 'unknown',
        'phenotype': 'test (HP:0123)',
        'zygosity': 'test',
        'variant_inheritance': 'test',
        'source_type': 'abstract',
    }

    observation = Observation(
        variant=HGVSVariant(
            hgvs_desc=fields['hgvs_c'],
            gene_symbol=fields['gene'],
            refseq=fields['transcript'],
            refseq_predicted=True,
            valid=fields['valid'] == 'True',
            validation_error=fields['validation_error'],
            protein_consequence=None,
            coding_equivalents=[],
        ),
        individual='unknown',
        texts=[
            TextSection('TEST', 'test', 0, 'Here is the observation text.', 'unknown')
        ],
        variant_descriptions=fields['paper_variant'].split(', '),
        patient_descriptions=['unknown'],
        paper_id=fields['paper_id'],
    )

    prompts = mock_prompt(
        {'zygosity': fields['zygosity']},
        {'variant_inheritance': fields['variant_inheritance']},
        {'phenotypes': ['test']},  # phenotypes_all, only one text, so only once.
        {
            'phenotypes': ['test']
        },  # phenotypes_observation, only one text, so only once.
        {'phenotypes': ['test']},  # phenotypes_acronyms, only one text, so only once.
        {'match': 'test (HP:0123)'},
    )
    pheno_searcher = mock_phenotype_searcher(
        [{'id': 'HP:0123', 'name': 'test', 'definition': 'test', 'synonyms': 'test'}]
    )
    pheno_fetcher = mock_phenotype_fetcher()
    content_extractor = PromptBasedContentExtractor(
        list(fields.keys()),
        prompts,
        mock_observation([observation]),
        pheno_searcher,
        pheno_fetcher,
    )
    content = content_extractor.extract(paper, fields['gene'])

    assert prompts.call_count('prompt_json') == 6
    assert len(content) == 1
    for key in fields:
        assert content[0][key] == fields[key]


def test_prompt_based_content_extractor_unsupported_field(
    paper: Paper,
    mock_prompt: Any,
    mock_observation: Any,
    mock_phenotype_searcher: Any,
    mock_phenotype_fetcher: Any,
) -> None:
    fields = {'unsupported_field': 'unsupported_value'}

    observation = Observation(
        variant=HGVSVariant(
            hgvs_desc='hgvs_desc',
            gene_symbol='gene',
            refseq='transcript',
            refseq_predicted=True,
            valid=True,
            validation_error='',
            protein_consequence=None,
            coding_equivalents=[],
        ),
        individual='unknown',
        texts=[
            TextSection('TEST', 'test', 0, 'Here is the observation text.', 'unknown')
        ],
        variant_descriptions=['hgvs_desc'],
        patient_descriptions=['unknown'],
        paper_id='paper_id',
    )

    content_extractor = PromptBasedContentExtractor(
        list(fields.keys()),
        mock_prompt({}),
        mock_observation([observation]),
        mock_phenotype_searcher([]),
        mock_phenotype_fetcher(),
    )
    with pytest.raises(ValueError):
        _ = content_extractor.extract(paper, 'test')


def test_prompt_based_content_extractor_with_protein_consequence(
    paper: Paper,
    mock_prompt: Any,
    mock_observation: Any,
    mock_phenotype_searcher: Any,
    mock_phenotype_fetcher: Any,
) -> None:
    fields = {
        'gene': 'CHI3L1',
        'paper_id': '12345678',
        'hgvs_c': 'c.1234A>G',
        'hgvs_p': 'p.Ala123Gly',
        'paper_variant': 'c.1234A>G, c.1234 A > G',
        'individual_id': 'unknown',
    }

    protein_variant = HGVSVariant(
        fields['hgvs_p'], fields['gene'], 'transcript', True, True, None, None, []
    )

    observation = Observation(
        variant=HGVSVariant(
            fields['hgvs_c'],
            fields['gene'],
            'transcript',
            True,
            True,
            None,
            protein_variant,
            [],
        ),
        individual=fields['individual_id'],
        texts=[
            TextSection('TEST', 'test', 0, 'Here is the observation text.', 'unknown')
        ],
        variant_descriptions=fields['paper_variant'].split(', '),
        patient_descriptions=[fields['individual_id']],
        paper_id=fields['paper_id'],
    )

    prompts = mock_prompt({})
    pheno_searcher = mock_phenotype_searcher([])
    pheno_fetcher = mock_phenotype_fetcher()
    content_extractor = PromptBasedContentExtractor(
        list(fields.keys()),
        prompts,
        mock_observation([observation]),
        pheno_searcher,
        pheno_fetcher,
    )
    content = content_extractor.extract(paper, fields['gene'])

    assert len(content) == 1
    for key in fields:
        assert content[0][key] == fields[key]


def test_prompt_based_content_extractor_invalid_model_response(
    paper: Paper,
    mock_prompt: Any,
    mock_observation: Any,
    mock_phenotype_searcher: Any,
    mock_phenotype_fetcher: Any,
) -> None:
    fields = {
        'gene': 'CHI3L1',
        'paper_id': '12345678',
        'hgvs_c': 'c.1234A>G',
        'paper_variant': 'c.1234A>G',
        'individual_id': 'unknown',
        'zygosity': 'failed',
    }

    observation = Observation(
        variant=HGVSVariant(
            fields['hgvs_c'], fields['gene'], 'transcript', True, True, None, None, []
        ),
        individual=fields['individual_id'],
        texts=[
            TextSection('TEST', 'test', 0, 'Here is the observation text.', 'unknown')
        ],
        variant_descriptions=fields['paper_variant'].split(', '),
        patient_descriptions=[fields['individual_id']],
        paper_id=fields['paper_id'],
    )

    prompts = mock_prompt({})
    pheno_searcher = mock_phenotype_searcher([])
    pheno_fetcher = mock_phenotype_fetcher()
    content_extractor = PromptBasedContentExtractor(
        list(fields.keys()),
        prompts,
        mock_observation([observation]),
        pheno_searcher,
        pheno_fetcher,
    )
    content = content_extractor.extract(paper, fields['gene'])

    assert len(content) == 1
    for key in fields:
        assert content[0][key] == fields[key]


def test_prompt_based_content_extractor_phenotype_empty_list(
    paper: Paper,
    mock_prompt: Any,
    mock_observation: Any,
    mock_phenotype_searcher: Any,
    mock_phenotype_fetcher: Any,
) -> None:
    fields = {
        'gene': 'CHI3L1',
        'paper_id': '12345678',
        'hgvs_c': 'c.1234A>G',
        'paper_variant': 'c.1234A>G',
        'individual_id': 'unknown',
        'phenotype': '',
    }

    observation = Observation(
        variant=HGVSVariant(
            fields['hgvs_c'], fields['gene'], 'transcript', True, True, None, None, []
        ),
        individual=fields['individual_id'],
        texts=[
            TextSection('TEST', 'test', 0, 'Here is the observation text.', 'unknown')
        ],
        variant_descriptions=fields['paper_variant'].split(', '),
        patient_descriptions=[fields['individual_id']],
        paper_id=fields['paper_id'],
    )

    prompts = mock_prompt(
        {'phenotypes': ['test']},  # phenotypes_all, only one text, so only once.
        {
            'phenotypes': ['test']
        },  # phenotypes_observation, only one text, so only once.
        {'phenotypes': []},  # phenotypes_acronyms, only one text, so only once.
    )
    content_extractor = PromptBasedContentExtractor(
        list(fields.keys()),
        prompts,
        mock_observation([observation]),
        mock_phenotype_searcher([]),
        mock_phenotype_fetcher(),
    )
    content = content_extractor.extract(paper, fields['gene'])

    assert len(content) == 1
    for key in fields:
        assert content[0][key] == fields[key]


def test_prompt_based_content_extractor_phenotype_hpo_description(
    paper: Paper,
    mock_prompt: Any,
    mock_observation: Any,
    mock_phenotype_searcher: Any,
    mock_phenotype_fetcher: Any,
) -> None:
    fields = {
        'gene': 'CHI3L1',
        'paper_id': '12345678',
        'hgvs_c': 'c.1234A>G',
        'paper_variant': 'c.1234A>G',
        'individual_id': 'unknown',
        'phenotype': 'test (HP:012345)',
    }

    observation = Observation(
        variant=HGVSVariant(
            fields['hgvs_c'], fields['gene'], 'transcript', True, True, None, None, []
        ),
        individual=fields['individual_id'],
        texts=[
            TextSection('TEST', 'test', 0, 'Here is the observation text.', 'unknown')
        ],
        variant_descriptions=fields['paper_variant'].split(', '),
        patient_descriptions=[fields['individual_id']],
        paper_id=fields['paper_id'],
    )

    prompts = mock_prompt(
        {'phenotypes': ['test']},  # phenotypes_all, only one text, so only once.
        {
            'phenotypes': ['test']
        },  # phenotypes_observation, only one text, so only once.
        {
            'phenotypes': ['HP:012345']
        },  # phenotypes_acronyms, only one text, so only once.
    )

    phenotype_fetcher = mock_phenotype_fetcher({'id': 'HP:012345', 'name': 'test'})
    content_extractor = PromptBasedContentExtractor(
        list(fields.keys()),
        prompts,
        mock_observation([observation]),
        mock_phenotype_searcher([]),
        phenotype_fetcher,
    )
    content = content_extractor.extract(paper, fields['gene'])

    assert len(content) == 1
    for key in fields:
        assert content[0][key] == fields[key]


def test_prompt_based_content_extractor_phenotype_empty_pheno_search(
    paper: Paper,
    mock_prompt: Any,
    mock_observation: Any,
    mock_phenotype_searcher: Any,
    mock_phenotype_fetcher: Any,
) -> None:
    fields = {
        'gene': 'CHI3L1',
        'paper_id': '12345678',
        'hgvs_c': 'c.1234A>G',
        'paper_variant': 'c.1234A>G',
        'individual_id': 'unknown',
        'phenotype': 'test',
    }

    observation = Observation(
        variant=HGVSVariant(
            fields['hgvs_c'], fields['gene'], 'transcript', True, True, None, None, []
        ),
        individual=fields['individual_id'],
        texts=[
            TextSection('TEST', 'test', 0, 'Here is the observation text.', 'unknown')
        ],
        variant_descriptions=fields['paper_variant'].split(', '),
        patient_descriptions=[fields['individual_id']],
        paper_id=fields['paper_id'],
    )

    prompts = mock_prompt(
        {'phenotypes': ['test']},  # phenotypes_all, only one text, so only once.
        {
            'phenotypes': ['test']
        },  # phenotypes_observation, only one text, so only once.
        {'phenotypes': ['test']},  # phenotypes_acronyms, only one text, so only once.
        {},  # phenotypes_simplify, only one text, so only once.
    )

    content_extractor = PromptBasedContentExtractor(
        list(fields.keys()),
        prompts,
        mock_observation([observation]),
        mock_phenotype_searcher([]),
        mock_phenotype_fetcher({}),
    )
    content = content_extractor.extract(paper, fields['gene'])

    assert len(content) == 1
    for key in fields:
        assert content[0][key] == fields[key]


def test_prompt_based_content_extractor_phenotype_simplification(
    paper: Paper,
    mock_prompt: Any,
    mock_observation: Any,
    mock_phenotype_searcher: Any,
    mock_phenotype_fetcher: Any,
) -> None:
    fields = {
        'gene': 'CHI3L1',
        'paper_id': '12345678',
        'hgvs_c': 'c.1234A>G',
        'paper_variant': 'c.1234A>G',
        'individual_id': 'unknown',
        'phenotype': 'test_simplified (HP:0321)',
    }

    observation = Observation(
        variant=HGVSVariant(
            fields['hgvs_c'], fields['gene'], 'transcript', True, True, None, None, []
        ),
        individual=fields['individual_id'],
        texts=[
            TextSection('TEST', 'test', 0, 'Here is the observation text.', 'unknown')
        ],
        variant_descriptions=fields['paper_variant'].split(', '),
        patient_descriptions=[fields['individual_id']],
        paper_id=fields['paper_id'],
    )

    prompts = mock_prompt(
        {'phenotypes': ['test']},  # phenotypes_all, only one text, so only once.
        {
            'phenotypes': ['test']
        },  # phenotypes_observation, only one text, so only once.
        {'phenotypes': ['test']},  # phenotypes_acronyms, only one text, so only once.
        {},  # phenotypes_candidates, initial value
        {
            'simplified': ['test_simplified']
        },  # phenotypes_simplify, only one text, so only once.
        {
            'match': 'test_simplified (HP:0321)'
        },  # phenotypes_candidates, simplified value
    )

    pheno_searcher = mock_phenotype_searcher(
        [{'id': 'HP:0123', 'name': 'test', 'definition': 'test', 'synonyms': 'test'}],
        [
            {
                'id': 'HP:0321',
                'name': 'test_simplified',
                'definition': 'test',
                'synonyms': 'test',
            }
        ],
    )
    content_extractor = PromptBasedContentExtractor(
        list(fields.keys()),
        prompts,
        mock_observation([observation]),
        pheno_searcher,
        mock_phenotype_fetcher({}),
    )
    content = content_extractor.extract(paper, fields['gene'])

    assert len(content) == 1
    for key in fields:
        assert content[0][key] == fields[key]


def test_prompt_based_content_extractor_phenotype_no_results_in_text(
    paper: Paper,
    mock_prompt: Any,
    mock_observation: Any,
    mock_phenotype_searcher: Any,
    mock_phenotype_fetcher: Any,
) -> None:
    fields = {
        'gene': 'CHI3L1',
        'paper_id': '12345678',
        'hgvs_c': 'c.1234A>G',
        'paper_variant': 'c.1234A>G',
        'individual_id': 'unknown',
        'phenotype': '',
    }

    observation = Observation(
        variant=HGVSVariant(
            fields['hgvs_c'], fields['gene'], 'transcript', True, True, None, None, []
        ),
        individual=fields['individual_id'],
        texts=[
            TextSection('TEST', 'test', 0, 'Here is the observation text.', 'unknown')
        ],
        variant_descriptions=fields['paper_variant'].split(', '),
        patient_descriptions=[fields['individual_id']],
        paper_id=fields['paper_id'],
    )

    prompts = mock_prompt(
        {'phenotypes': []},  # phenotypes_all, only one text, so only once.
    )

    content_extractor = PromptBasedContentExtractor(
        list(fields.keys()),
        prompts,
        mock_observation([observation]),
        mock_phenotype_searcher([]),
        mock_phenotype_fetcher({}),
    )
    content = content_extractor.extract(paper, fields['gene'])

    assert len(content) == 1
    for key in fields:
        assert content[0][key] == fields[key]


def test_prompt_based_content_extractor_phenotype_no_results_for_observation(
    paper: Paper,
    mock_prompt: Any,
    mock_observation: Any,
    mock_phenotype_searcher: Any,
    mock_phenotype_fetcher: Any,
) -> None:
    fields = {
        'gene': 'CHI3L1',
        'paper_id': '12345678',
        'hgvs_c': 'c.1234A>G',
        'paper_variant': 'c.1234A>G',
        'individual_id': 'unknown',
        'phenotype': '',
    }

    observation = Observation(
        variant=HGVSVariant(
            fields['hgvs_c'], fields['gene'], 'transcript', True, True, None, None, []
        ),
        individual=fields['individual_id'],
        texts=[
            TextSection('TEST', 'test', 0, 'Here is the observation text.', 'unknown')
        ],
        variant_descriptions=fields['paper_variant'].split(', '),
        patient_descriptions=[fields['individual_id']],
        paper_id=fields['paper_id'],
    )

    prompts = mock_prompt(
        {'phenotypes': ['test']},  # phenotypes_all, only one text, so only once.
        {'phenotypes': []},  # phenotypes_obs, only one text, so only once.
    )

    content_extractor = PromptBasedContentExtractor(
        list(fields.keys()),
        prompts,
        mock_observation([observation]),
        mock_phenotype_searcher([]),
        mock_phenotype_fetcher({}),
    )
    content = content_extractor.extract(paper, fields['gene'])

    assert len(content) == 1
    for key in fields:
        assert content[0][key] == fields[key]


def test_prompt_based_content_extractor_phenotype_specific_individual(
    paper: Paper,
    mock_prompt: Any,
    mock_observation: Any,
    mock_phenotype_searcher: Any,
    mock_phenotype_fetcher: Any,
) -> None:
    fields = {
        'gene': 'CHI3L1',
        'paper_id': '12345678',
        'hgvs_c': 'c.1234A>G',
        'paper_variant': 'c.1234A>G',
        'individual_id': 'proband',
        'phenotype': '',
    }

    observation = Observation(
        variant=HGVSVariant(
            fields['hgvs_c'], fields['gene'], 'transcript', True, True, None, None, []
        ),
        individual=fields['individual_id'],
        texts=[
            TextSection('TEST', 'test', 0, 'Here is the observation text.', 'unknown')
        ],
        variant_descriptions=fields['paper_variant'].split(', '),
        patient_descriptions=[fields['individual_id']],
        paper_id=fields['paper_id'],
    )

    prompts = mock_prompt(
        {'phenotypes': []},  # phenotypes_all, only one text, so only once.
    )

    content_extractor = PromptBasedContentExtractor(
        list(fields.keys()),
        prompts,
        mock_observation([observation]),
        mock_phenotype_searcher([]),
        mock_phenotype_fetcher({}),
    )
    content = content_extractor.extract(paper, fields['gene'])

    assert len(content) == 1
    for key in fields:
        assert content[0][key] == fields[key]


def test_prompt_based_content_extractor_phenotype_table_texts(
    paper: Paper,
    mock_prompt: Any,
    mock_observation: Any,
    mock_phenotype_searcher: Any,
    mock_phenotype_fetcher: Any,
) -> None:
    fields = {
        'gene': 'CHI3L1',
        'paper_id': '12345678',
        'hgvs_c': 'c.1234A>G',
        'paper_variant': 'c.1234A>G',
        'individual_id': 'unknown',
        'phenotype': '',
    }

    observation = Observation(
        variant=HGVSVariant(
            fields['hgvs_c'], fields['gene'], 'transcript', True, True, None, None, []
        ),
        individual=fields['individual_id'],
        texts=[
            TextSection('TEST', 'test', 0, 'Here is the observation text.', 'unknown'),
            TextSection('TABLE', 'table', 0, 'Here is the table text.', 'unknown'),
        ],
        variant_descriptions=fields['paper_variant'].split(', '),
        patient_descriptions=[fields['individual_id']],
        paper_id=fields['paper_id'],
    )

    prompts = mock_prompt(
        {'phenotypes': []},  # phenotypes_all, two texts
        {'phenotypes': []},  # phenotypes_all
    )

    content_extractor = PromptBasedContentExtractor(
        list(fields.keys()),
        prompts,
        mock_observation([observation]),
        mock_phenotype_searcher([]),
        mock_phenotype_fetcher({}),
    )
    content = content_extractor.extract(paper, fields['gene'])

    assert prompts.call_count('prompt_json') == 2  # ensure both prompts were used.
    assert len(content) == 1
    for key in fields:
        assert content[0][key] == fields[key]


def test_prompt_based_content_extractor_json_prompt_response(
    paper: Paper,
    mock_prompt: Any,
    mock_observation: Any,
    mock_phenotype_searcher: Any,
    mock_phenotype_fetcher: Any,
) -> None:
    fields = {
        'gene': 'CHI3L1',
        'paper_id': '12345678',
        'hgvs_c': 'c.1234A>G',
        'paper_variant': 'c.1234A>G',
        'individual_id': 'unknown',
        'zygosity': {'zygosity': {'key': 'value'}},
    }

    observation = Observation(
        variant=HGVSVariant(
            fields['hgvs_c'], fields['gene'], 'transcript', True, True, None, None, []
        ),
        individual=fields['individual_id'],
        texts=[
            TextSection('TEST', 'test', 0, 'Here is the observation text.', 'unknown')
        ],
        variant_descriptions=fields['paper_variant'].split(', '),
        patient_descriptions=[fields['individual_id']],
        paper_id=fields['paper_id'],
    )

    prompts = mock_prompt(fields['zygosity'])
    content_extractor = PromptBasedContentExtractor(
        list(fields.keys()),
        prompts,
        mock_observation([observation]),
        mock_phenotype_searcher,
        mock_phenotype_fetcher,
    )
    content = content_extractor.extract(paper, fields['gene'])

    assert len(content) == 1
    assert content[0]['zygosity'] == '{"key": "value"}'


def test_prompt_based_content_extractor_functional_study(
    paper: Paper,
    mock_prompt: Any,
    mock_observation: Any,
    mock_phenotype_searcher: Any,
    mock_phenotype_fetcher: Any,
) -> None:
    fields = {
        'gene': 'CHI3L1',
        'paper_id': '12345678',
        'hgvs_c': 'c.1234A>G',
        'paper_variant': 'c.1234A>G',
        'individual_id': 'unknown',
        'engineered_cells': 'True',
        'patient_cells_tissues': 'True',
        'animal_model': 'False',
    }

    observation = Observation(
        variant=HGVSVariant(
            hgvs_desc=fields['hgvs_c'],
            gene_symbol=fields['gene'],
            refseq='transcript',
            refseq_predicted=True,
            valid=True,
            validation_error='',
            protein_consequence=None,
            coding_equivalents=[],
        ),
        individual='unknown',
        texts=[
            TextSection('TEST', 'test', 0, 'Here is the observation text.', 'unknown')
        ],
        variant_descriptions=fields['paper_variant'].split(', '),
        patient_descriptions=['unknown'],
        paper_id=fields['paper_id'],
    )

    prompts = mock_prompt(
        {'functional_study': ['cell line', 'patient cells']},
        {'functional_study': ['patient cells']},
        {'functional_study': ['none']},
    )
    content_extractor = PromptBasedContentExtractor(
        list(fields.keys()),
        prompts,
        mock_observation([observation]),
        mock_phenotype_searcher(),
        mock_phenotype_fetcher(),
    )
    content = content_extractor.extract(paper, fields['gene'])

    assert len(content) == 1
    for key in fields:
        assert content[0][key] == fields[key]


def test_prompt_based_content_extractor_field_caching_phenotype(
    paper: Paper,
    mock_prompt: Any,
    mock_observation: Any,
    mock_phenotype_searcher: Any,
    mock_phenotype_fetcher: Any,
) -> None:
    paper_id = '12345678'
    phenotype = 'test i1 (HP:0123)'

    variant1 = HGVSVariant(
        hgvs_desc='c.1234A>G',
        gene_symbol='CHI3L1',
        refseq='transcript',
        refseq_predicted=True,
        valid=True,
        validation_error='',
        protein_consequence=None,
        coding_equivalents=[],
    )

    variant2 = HGVSVariant(
        hgvs_desc='c.4321G>T',
        gene_symbol='CHI3L1',
        refseq='transcript',
        refseq_predicted=True,
        valid=True,
        validation_error='',
        protein_consequence=None,
        coding_equivalents=[],
    )

    observation1 = Observation(
        variant=variant1,
        individual='I-1',
        texts=[
            TextSection('TEST', 'test', 0, 'Here is the observation text.', 'unknown')
        ],
        variant_descriptions=['c.1234A>G'],
        patient_descriptions=['I-1'],
        paper_id=paper_id,
    )

    observation2 = Observation(
        variant=variant2,
        individual='I-1',
        texts=[
            TextSection('TEST', 'test', 0, 'Here is the observation text.', 'unknown')
        ],
        variant_descriptions=['c.4321G>T'],
        patient_descriptions=['I-1'],
        paper_id=paper_id,
    )

    prompts = mock_prompt(
        {'phenotypes': ['test']},  # phenotypes_all, only one text, so only once.
        {
            'phenotypes': ['test']
        },  # phenotypes_observation, only one text, so only once.
        {'phenotypes': ['test']},  # phenotypes_acronyms, only one text, so only once.
        {'match': 'test i1 (HP:0123)'},
    )
    observation_finder = mock_observation([observation1, observation2])

    pheno_searcher = mock_phenotype_searcher(
        [
            {
                'id': 'HP:0123',
                'name': 'test i1',
                'definition': 'test',
                'synonyms': 'test',
            }
        ],
    )
    pheno_fetcher = mock_phenotype_fetcher()
    content_extractor = PromptBasedContentExtractor(
        ['phenotype'], prompts, observation_finder, pheno_searcher, pheno_fetcher
    )
    content = content_extractor.extract(paper, 'CHI3L1')

    assert len(content) == 2
    assert content[0]['phenotype'] == phenotype
    assert content[1]['phenotype'] == phenotype


def test_prompt_based_content_extractor_field_caching_variant_type(
    paper: Paper,
    mock_prompt: Any,
    mock_observation: Any,
    mock_phenotype_searcher: Any,
    mock_phenotype_fetcher: Any,
) -> None:
    paper_id = '12345678'
    variant_type = 'missense'

    variant = HGVSVariant(
        hgvs_desc='c.1234A>G',
        gene_symbol='CHI3L1',
        refseq='transcript',
        refseq_predicted=True,
        valid=True,
        validation_error='',
        protein_consequence=None,
        coding_equivalents=[],
    )

    observation1 = Observation(
        variant=variant,
        individual='I-1',
        texts=[
            TextSection('TEST', 'test', 0, 'Here is the observation text.', 'unknown')
        ],
        variant_descriptions=['c.1234A>G'],
        patient_descriptions=['I-1'],
        paper_id=paper_id,
    )

    observation2 = Observation(
        variant=variant,
        individual='I-2',
        texts=[
            TextSection('TEST', 'test', 0, 'Here is the observation text.', 'unknown')
        ],
        variant_descriptions=['c.1234A>G'],
        patient_descriptions=['I-2'],
        paper_id=paper_id,
    )
    prompts = mock_prompt(
        # o1 variant_type
        {'variant_type': variant_type},
    )
    observation_finder = mock_observation([observation1, observation2])
    pheno_searcher = mock_phenotype_searcher()
    pheno_fetcher = mock_phenotype_fetcher()
    content_extractor = PromptBasedContentExtractor(
        ['variant_type'], prompts, observation_finder, pheno_searcher, pheno_fetcher
    )
    content = content_extractor.extract(paper, 'CHI3L1')

    assert len(content) == 2
    assert content[0]['variant_type'] == variant_type
    assert content[1]['variant_type'] == variant_type


def test_prompt_based_content_extractor_field_caching_study_type(
    paper: Paper,
    mock_prompt: Any,
    mock_observation: Any,
    mock_phenotype_searcher: Any,
    mock_phenotype_fetcher: Any,
) -> None:
    paper_id = '12345678'
    study_type = 'case study'

    variant1 = HGVSVariant(
        hgvs_desc='c.1234A>G',
        gene_symbol='CHI3L1',
        refseq='transcript',
        refseq_predicted=True,
        valid=True,
        validation_error='',
        protein_consequence=None,
        coding_equivalents=[],
    )

    variant2 = HGVSVariant(
        hgvs_desc='c.4321T>G',
        gene_symbol='CHI3L1',
        refseq='transcript',
        refseq_predicted=True,
        valid=True,
        validation_error='',
        protein_consequence=None,
        coding_equivalents=[],
    )

    observation1 = Observation(
        variant=variant1,
        individual='I-1',
        texts=[
            TextSection('TEST', 'test', 0, 'Here is the observation text.', 'unknown')
        ],
        variant_descriptions=['c.1234A>G'],
        patient_descriptions=['I-1'],
        paper_id=paper_id,
    )

    observation2 = Observation(
        variant=variant2,
        individual='I-2',
        texts=[
            TextSection('TEST', 'test', 0, 'Here is the observation text.', 'unknown')
        ],
        variant_descriptions=['c.4321T>G'],
        patient_descriptions=['I-2'],
        paper_id=paper_id,
    )
    prompts = mock_prompt(
        {'study_type': study_type},
    )
    observation_finder = mock_observation([observation1, observation2])
    pheno_searcher = mock_phenotype_searcher()
    pheno_fetcher = mock_phenotype_fetcher()
    content_extractor = PromptBasedContentExtractor(
        ['study_type'], prompts, observation_finder, pheno_searcher, pheno_fetcher
    )
    content = content_extractor.extract(paper, 'CHI3L1')

    assert len(content) == 2
    assert content[0]['study_type'] == study_type
    assert content[1]['study_type'] == study_type


def test_prompt_based_content_extractor_unprocessable_paper(
    paper: Paper,
    mock_prompt: Any,
    mock_observation: Any,
    mock_phenotype_searcher: Any,
    mock_phenotype_fetcher: Any,
) -> None:
    paper.props['can_access'] = False
    content_extractor = PromptBasedContentExtractor(
        [],
        mock_prompt({}),
        mock_observation([]),
        mock_phenotype_searcher,
        mock_phenotype_fetcher,
    )
    content = content_extractor.extract(paper, 'CHI3L1')
    assert content == []


def test_prompt_based_content_extractor_no_observations(
    paper: Paper,
    mock_prompt: Any,
    mock_observation: Any,
    mock_phenotype_searcher: Any,
    mock_phenotype_fetcher: Any,
) -> None:
    content_extractor = PromptBasedContentExtractor(
        [],
        mock_prompt({}),
        mock_observation([]),
        mock_phenotype_searcher,
        mock_phenotype_fetcher,
    )
    content = content_extractor.extract(paper, 'CHI3L1')
    assert content == []


xmldoc = """
    <document>
        <id>7933980</id>
        {content}
    </document>
"""


def test_fulltext() -> None:
    xml1 = """
        <passage>
            <infon key="section_type">TITLE</infon>
            <infon key="type">front</infon>
            <offset>0</offset>
            <text>test
                title</text>
        </passage>
"""
    assert get_fulltext(None) == ''
    assert get_fulltext(xmldoc.format(content=xml1), include=['TITLE']) == 'test title'
    assert get_fulltext(xmldoc.format(content=xml1), exclude=['TITLE']) == ''
    assert (
        get_fulltext(xmldoc.format(content=xml1), include=['TITLE'], exclude=['TITLE'])
        == ''
    )


def test_fulltext_missing() -> None:
    xml1 = """
        <passage>
        </passage>
"""
    xml2 = """
        <passage>
            <infon key="section_type">TITLE</infon>
        </passage>
"""
    xml3 = """
        <passage>
            <infon key="section_type">TITLE</infon>
            <infon key="type">front</infon>
        </passage>
"""
    with pytest.raises(ValueError) as e:
        get_fulltext(xmldoc.format(content=xml1))
    assert (
        str(e.value)
        == "Missing 'section_type' infon element in passage for document 7933980"
    )
    with pytest.raises(ValueError) as e:
        get_fulltext(xmldoc.format(content=xml2))
    assert (
        str(e.value) == "Missing 'type' infon element in passage for document 7933980"
    )
    with pytest.raises(ValueError) as e:
        get_fulltext(xmldoc.format(content=xml3))
    assert (
        str(e.value)
        == "Missing 'offset' infon element in TITLE passage for document 7933980"
    )
    assert (
        str(e.value)
        == "Missing 'offset' infon element in TITLE passage for document 7933980"
    )
    assert (
        str(e.value)
        == "Missing 'offset' infon element in TITLE passage for document 7933980"
    )
    assert (
        str(e.value)
        == "Missing 'offset' infon element in TITLE passage for document 7933980"
    )
