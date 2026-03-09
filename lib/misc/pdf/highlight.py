import json
import math
from pathlib import Path
from typing import Any, cast

import fitz
from rapidfuzz import fuzz

from lib.misc.pdf.paths import pdf_highlighted_path, pdf_raw_path, pdf_words_json_path


def parse_hex_color(color_str: str) -> tuple[float, float, float]:
    if color_str.startswith('#'):
        hex_str = color_str.lstrip('#')
        if len(hex_str) == 6:
            try:
                r = int(hex_str[0:2], 16) / 255.0
                g = int(hex_str[2:4], 16) / 255.0
                b = int(hex_str[4:6], 16) / 255.0
                return (r, g, b)
            except ValueError:
                pass

    raise ValueError(
        f'Invalid color: "{color_str}". Use a color name (e.g., "yellow"), '
        'hex code (e.g., "#FF0000"), or RGB tuple (0-1).'
    )


def find_best_match(query: str, paper_id: str) -> list[list[int | float | str]] | None:
    def normalize(token: str) -> str:
        """Normalize tokens to improve fuzzy matching."""
        token = token.replace('\u00ad', '')  # remove soft hyphen
        token = token.replace('\u2010', '-')  # hyphen
        token = token.replace('\u2011', '-')  # non-breaking hyphen
        token = token.replace('\u2012', '-')  # figure dash
        token = token.replace('\u2013', '-')  # en dash
        token = token.replace('\u2014', '-')  # em dash
        token = token.replace('\u2015', '-')  # horizontal bar
        return token

    def fuzzy_match(a: str, b: str, threshold: int = 80) -> bool:
        """Return True if tokens are similar enough."""
        if not a or not b:
            return False
        return fuzz.partial_ratio(a, b) >= threshold

    def gap_penalty(gap: int) -> float:
        return math.log1p(gap) / 2

    """
    Finds the best match of a query string in a PDF word list, allowing skipped words.
    Returns the matched words (as dictionaries/lists) with the minimal total gap.
    """

    # Load words from JSON
    with open(pdf_words_json_path(paper_id), 'r') as f:
        words = json.load(f)

    tokens = query.split()
    n = len(words)

    best_match = None
    best_score = None

    for start_idx, word in enumerate(words):
        word_norm = normalize(word[1])
        if not fuzzy_match(word_norm, tokens[0]):
            continue

        match_words = [word]
        prev_idx = start_idx
        gap = 0
        similarity_sum = fuzz.partial_ratio(word_norm, tokens[0]) / 100
        token_idx = 1

        for j in range(start_idx + 1, n):
            if token_idx >= len(tokens):
                break

            word_norm = normalize(words[j][1])
            if fuzzy_match(word_norm, tokens[token_idx]):
                gap += j - prev_idx - 1
                prev_idx = j
                similarity_sum += fuzz.partial_ratio(word_norm, tokens[token_idx]) / 100
                match_words.append(words[j])
                token_idx += 1

        if token_idx == len(tokens):
            score = similarity_sum - gap_penalty(gap)
            if best_score is None or score > best_score:
                best_score = score
                best_match = match_words
    return best_match


def highlight_words_in_pdf(
    paper_id: str,
    words: list[list[int | float | str]],
    color: tuple[float, float, float],
) -> Path:
    """
    Highlight words in a PDF at their bounding box locations.

    Args:
        paper_id: The paper ID to identify the PDF file
        words: List of word entries with format [word_id, text, page, x0, y0, x1, y1, x2, y2, x3, y3]
        color: RGB tuple with values 0-1

    Returns:
        Path to the highlighted PDF file
    """
    # Load PDF
    pdf_path = pdf_raw_path(paper_id)
    pdf_doc = fitz.open(pdf_path)

    # Group words by page
    words_by_page: dict[int | float, list[list[int | float | str]]] = {}
    for word in words:
        page = int(word[2])
        if page not in words_by_page:
            words_by_page[page] = []
        words_by_page[page].append(word)

    # Highlight words on each page
    for page_num, page_words in words_by_page.items():
        page = cast(Any, pdf_doc)[int(page_num)]  # type: ignore[index]
        for word in page_words:
            # Extract coordinates: [word_id, text, page, x0, y0, x1, y1, x2, y2, x3, y3]
            x0 = float(word[3])
            y0 = float(word[4])
            x1 = float(word[5])
            y1 = float(word[6])
            rect = fitz.Rect(x0, y0, x1, y1)
            page.draw_rect(rect, color=color, fill=color, fill_opacity=0.3)  # type: ignore[attr-defined]

    # Save highlighted PDF
    output_path = pdf_highlighted_path(paper_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_doc.save(output_path)
    pdf_doc.close()

    return output_path
