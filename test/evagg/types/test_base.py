from lib.evagg.types import Paper


def test_paper_from_dict() -> None:
    paper_dict = {
        'id': 'pmid:123',
        'citation': 'Test Citation',
        'abstract': 'Test Abstract',
        'pmcid': 'PMC123',
        'content': b'',
    }
    paper = Paper(**paper_dict)
    assert paper.id == 'pmid:123'
    assert paper.citation == 'Test Citation'
    assert paper.abstract == 'Test Abstract'
    assert paper.pmcid == 'PMC123'


def test_paper_equality() -> None:
    paper_dict = {
        'id': 'pmid:123',
        'citation': 'Test Citation',
        'abstract': 'Test Abstract',
        'pmcid': 'PMC123',
        'content': b'',
    }
    same_paper_dict = paper_dict.copy()
    different_paper_dict = paper_dict.copy()
    different_paper_dict['id'] = '456'

    paper = Paper(**paper_dict)
    same_paper = Paper(**same_paper_dict)
    different_paper = Paper(**different_paper_dict)

    assert paper == paper
    assert paper == same_paper
    assert paper != different_paper
    assert paper != 'not a paper'
    assert len({paper, same_paper, different_paper}) == 2


def test_paper_repr() -> None:
    paper_dict = {
        'id': 'pmid:123',
        'citation': 'Test Citation',
        'abstract': 'Test Abstract',
        'pmcid': 'PMC123',
        'content': b'',
    }
    str_paper = 'id: pmid:123 - "Test Citation"'

    paper = Paper(**paper_dict)
    assert str(paper) == str_paper
