import json

import pytest

from lib.misc.pdf.highlight import find_best_match
from lib.misc.pdf.parse import WordLoc
from lib.misc.pdf.paths import pdf_words_json_path


@pytest.fixture
def mock_pdf_words(mocked_root_dir, test_file_contents):
    """Create mock PDF words JSON file in the mocked root directory."""
    paper_id = 'test_paper_123'

    # Create directory structure using pdf_words_json_path
    words_file = pdf_words_json_path(paper_id)
    words_file.parent.mkdir(parents=True, exist_ok=True)

    # Load and write mock JSON file
    mock_words_content = test_file_contents('mock_pdf_words.json')
    words_file.write_text(mock_words_content)

    return paper_id


def test_minimal_gap_selection(mock_pdf_words):
    """Test finding best match with minimal gaps."""
    # Load words from the mock file
    words_file = pdf_words_json_path(mock_pdf_words)
    with open(words_file, 'r') as f:
        words = json.load(f)
        words = [WordLoc(**w) for w in words]

    query = 'Nature Publishing Group Science'
    result = find_best_match(query, words)

    # The best match should be the second "Nature" occurrence
    expected_word_ids = [6, 7, 8, 9]
    expected_texts = ['Nature', 'Publishing', 'Grou', 'Scienes.']  # Note fuzzy matches.

    assert result is not None
    assert [w.word for w in result] == expected_texts
    assert [w.page_idx for w in result] == expected_word_ids


@pytest.fixture
def mock_pdf_words_with_page_break(mocked_root_dir):
    """Create mock PDF words JSON with spans on different pages separated by a break."""
    paper_id = 'test_paper_page_break'

    # Create mock words with WordLoc-compatible field names
    # [page_idx, word, x0, y0, x1, y1, x2, y2, x3, y3]
    padding_words = [
        {
            'page_idx': 1,
            'word': 'Background',
            'x0': 0,
            'y0': 10.0,
            'x1': 10.0,
            'y1': 100.0,
            'x2': 25.0,
            'y2': 0,
            'x3': 0,
            'y3': 0,
        },
    ]

    # Words on page 1: "rare genetic disorder" with OCR noise
    page1_words = [
        {
            'page_idx': 1,
            'word': 'rar3',
            'x0': 0,
            'y0': 50.0,
            'x1': 50.0,
            'y1': 120.0,
            'x2': 65.0,
            'y2': 0,
            'x3': 0,
            'y3': 0,
        },
        {
            'page_idx': 1,
            'word': 'genetic',
            'x0': 0,
            'y0': 130.0,
            'x1': 50.0,
            'y1': 220.0,
            'x2': 65.0,
            'y2': 0,
            'x3': 0,
            'y3': 0,
        },
        {
            'page_idx': 1,
            'word': 'd1sorder',
            'x0': 0,
            'y0': 230.0,
            'x1': 50.0,
            'y1': 330.0,
            'x2': 65.0,
            'y2': 0,
            'x3': 0,
            'y3': 0,
        },
    ]

    # Words on page 2: "affects patients severely" with OCR noise
    page2_words = [
        {
            'page_idx': 2,
            'word': 'Nature',
            'x0': 0,
            'y0': 50.0,
            'x1': 100.0,
            'y1': 130.0,
            'x2': 115.0,
            'y2': 0,
            'x3': 0,
            'y3': 0,
        },
        {
            'page_idx': 2,
            'word': 'Publishing',
            'x0': 0,
            'y0': 140.0,
            'x1': 100.0,
            'y1': 250.0,
            'x2': 115.0,
            'y2': 0,
            'x3': 0,
            'y3': 0,
        },
        {
            'page_idx': 2,
            'word': 'Group',
            'x0': 0,
            'y0': 260.0,
            'x1': 100.0,
            'y1': 360.0,
            'x2': 115.0,
            'y2': 0,
            'x3': 0,
            'y3': 0,
        },
        {
            'page_idx': 2,
            'word': 'affect5',
            'x0': 0,
            'y0': 50.0,
            'x1': 100.0,
            'y1': 130.0,
            'x2': 115.0,
            'y2': 0,
            'x3': 0,
            'y3': 0,
        },
        {
            'page_idx': 2,
            'word': 'p@tients',
            'x0': 0,
            'y0': 140.0,
            'x1': 100.0,
            'y1': 250.0,
            'x2': 115.0,
            'y2': 0,
            'x3': 0,
            'y3': 0,
        },
        {
            'page_idx': 2,
            'word': 'severity',
            'x0': 0,
            'y0': 260.0,
            'x1': 100.0,
            'y1': 360.0,
            'x2': 115.0,
            'y2': 0,
            'x3': 0,
            'y3': 0,
        },
    ]

    words = padding_words + page1_words + page2_words

    words_file = pdf_words_json_path(paper_id)
    words_file.parent.mkdir(parents=True, exist_ok=True)
    words_file.write_text(json.dumps(words))

    return paper_id


def test_noisy_spans_with_page_break(mock_pdf_words_with_page_break):
    """Test finding best match for two noisy spans separated by page break.

    Verifies that when query includes <SPLIT> to indicate a page break,
    the function correctly matches both parts with OCR-like noise.

    The query should include <SPLIT> to indicate where the page break occurs
    in the evidence text.
    """
    # Load words from the mock file
    words_file = pdf_words_json_path(mock_pdf_words_with_page_break)
    with open(words_file, 'r') as f:
        words = json.load(f)
        words = [WordLoc(**w) for w in words]

    # Query with page break: "rare genetic disorder <SPLIT> affects patients severity"
    # Should match noisy OCR versions across page 1 and page 2
    query = 'rare genetic disorder <SPLIT> affects patients severity'
    result = find_best_match(query, words)

    assert result is not None
    # Should match 6 words: page 1 (rar3, genetic, d1sorder) + page 2 (affect5, p@tients, severity)
    expected_texts = ['rar3', 'genetic', 'd1sorder', 'affect5', 'p@tients', 'severity']
    expected_page_ids = [1, 1, 1, 2, 2, 2]

    assert [w.word for w in result] == expected_texts
