from typing import Any

import pytest


from lib.evagg.library import SinglePaperLibrary
from lib.evagg.ref import IPaperLookupClient
from lib.evagg.types import Paper


@pytest.fixture
def mock_paper_client(mock_client: type) -> IPaperLookupClient:
    return mock_client(IPaperLookupClient)


def test_single_paper_library(mock_paper_client: Any):
    # NB: mocking should be improved to map queries to results.
    # a results iterable is likely insufficient!
    paper1 = Paper(id="1", citation="Paper 1", abstract="Abstract 1", pmid="pmid1")
    paper2a = Paper(id="2a", citation="Paper 2a", abstract="Abstract 2a", pmid="pmid2a")
    paper2b = Paper(id="2b", citation="Paper 2b", abstract="Abstract 2b", pmid="pmid2b")

    library = SinglePaperLibrary(
        mock_paper_client(paper1, paper2a, paper2b),
    )
    results1 = library.get_papers({"pmid": "pmid1"})
    assert len(results1) == 1
    assert paper1 in results1

    results2 = library.get_papers({"pmid": "pmid2a"})
    assert len(results2) == 1
    assert paper2a in results2
    assert paper2b not in results2
