import json
from pathlib import Path
from typing import Any, cast

import fitz

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
    best_gap = None

    # For each occurrence of the first token
    for start_idx, word in enumerate(words):
        if word[1] != tokens[0]:
            continue

        match_words = [word]  # store matched words
        prev_idx = (
            start_idx  # stores the index of the last matched token in the word list
        )
        gap = 0
        token_idx = 1  # next token to match

        # Scan forward through the rest of the words
        for j in range(start_idx + 1, n):
            if token_idx >= len(tokens):
                break  # matched all tokens

            if words[j][1] == tokens[token_idx]:
                gap += (
                    j - prev_idx - 1
                )  # counts the number of words skipped between the previous match and the current one.
                match_words.append(words[j])
                prev_idx = j
                token_idx += 1

        # If we matched all tokens, update best match if gap is smaller
        if token_idx == len(tokens):
            if best_gap is None or gap < best_gap:
                best_gap = gap
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
