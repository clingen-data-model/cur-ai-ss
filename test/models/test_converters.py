from lib.models import PaperDB, PaperExtractionOutput, PaperType


def test_apply_to_maps_all_fields():
    output = PaperExtractionOutput(
        title='A Novel Variant in BRCA1',
        first_author='Smith',
        journal_name='Nature Genetics',
        abstract='We describe a novel variant...',
        publication_year=2024,
        doi='10.1234/ng.5678',
        pmid='12345678',
        pmcid='PMC9999999',
        paper_types=[PaperType.Research, PaperType.Case_study],
    )
    paper_db = PaperDB(id='test-id', gene_id='1', filename='test.pdf')
    output.apply_to(paper_db)

    assert paper_db.title == 'A Novel Variant in BRCA1'
    assert paper_db.first_author == 'Smith'
    assert paper_db.journal_name == 'Nature Genetics'
    assert paper_db.abstract == 'We describe a novel variant...'
    assert paper_db.publication_year == 2024
    assert paper_db.doi == '10.1234/ng.5678'
    assert paper_db.pmid == '12345678'
    assert paper_db.pmcid == 'PMC9999999'
    assert paper_db.paper_types == ['Research', 'Case_study']


def test_apply_to_handles_none_fields():
    output = PaperExtractionOutput(
        title='Minimal Paper',
        first_author='Doe',
        journal_name=None,
        paper_types=[PaperType.Unknown],
    )
    paper_db = PaperDB(id='test-id-2', gene_id='1', filename='test2.pdf')
    output.apply_to(paper_db)

    assert paper_db.title == 'Minimal Paper'
    assert paper_db.first_author == 'Doe'
    assert paper_db.journal_name is None
    assert paper_db.abstract is None
    assert paper_db.publication_year is None
    assert paper_db.doi is None
    assert paper_db.pmid is None
    assert paper_db.pmcid is None
    assert paper_db.paper_types == ['Unknown']
