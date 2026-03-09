import pytest

from lib.misc.pdf.highlight import find_best_match
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
    query = 'Nature Publishing Group Science'
    result = find_best_match(query, mock_pdf_words)

    # The best match should be the second "Nature" occurrence
    expected_word_ids = [6, 7, 8, 9]
    expected_texts = ['Nature', 'Publishing', 'Group', 'Science']

    assert result is not None
    assert [w[1] for w in result] == expected_texts
    assert [w[0] for w in result] == expected_word_ids
