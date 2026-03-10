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

    raise ValueError(f'Invalid color: "{color_str}". Use a hex code (e.g., "#FF0000")')


def find_best_match(query: str, paper_id: str) -> list[list[int | float | str]] | None:
    """
    Finds the best match of a query in a PDF word list.
    Supports <SPLIT> for evidence spanning multiple pages/sections.
    """
    window_size = 5

    def normalize(token: str) -> str:
        """Normalize tokens to improve fuzzy matching."""
        token = token.lower()
        token = token.replace('\u00ad', '')  # soft hyphen
        token = token.replace('\u2010', '-')  # hyphen
        token = token.replace('\u2011', '-')  # non-breaking hyphen
        token = token.replace('\u2012', '-')  # figure dash
        token = token.replace('\u2013', '-')  # en dash
        token = token.replace('\u2014', '-')  # em dash
        token = token.replace('\u2015', '-')  # horizontal bar
        return token

    # Load words from JSON
    with open(pdf_words_json_path(paper_id), 'r') as f:
        words = json.load(f)
    n = len(words)

    # Split query on <SPLIT>
    parts = [p.strip() for p in query.split('<SPLIT>')]
    if not parts:
        return None

    full_span = []
    search_start = 0

    for part in parts:
        q_len = len(part.split())
        min_len, max_len = max(1, q_len - window_size), q_len + window_size
        best_score, best_span = 0, None
        query_norm = normalize(part)

        # Slide window over remaining words
        for i in range(search_start, n):
            for span_len in range(min_len, max_len + 1):
                j = i + span_len
                if j > n:
                    break
                span_text = ' '.join(normalize(w[1]) for w in words[i:j])
                score = fuzz.ratio(span_text, query_norm)
                if score > best_score:
                    best_score = score
                    best_span = (i, j - 1)

        if best_span is None:
            # if any part cannot be matched, return None
            return None

        i, j = best_span
        full_span.extend(words[i : j + 1])
        # For next part, start searching after the current match
        search_start = j + 1

    return full_span


def highlight_words_in_pdf(
    paper_id: str,
    words: list[list[int | float | str]],
    rgb_color: tuple[float, float, float],
) -> Path:
    """
    Highlight words in a PDF at their bounding box locations.

    Args:
        paper_id: The paper ID to identify the PDF file
        words: List of word entries with format [page_id, word, x0, y0, x1, y1, x2, y2, x3, y3]
        rgb_color: RGB tuple with values 0-1

    Returns:
        Path to the highlighted PDF file
    """

    # Load PDF
    pdf_path = pdf_highlighted_path(paper_id)
    pdf_doc = fitz.open(pdf_path)

    # Group words by page
    words_by_page: dict[int, list[list[int | float | str]]] = {}
    for word in words:
        page_id = int(word[0])
        if page_id not in words_by_page:
            words_by_page[page_id] = []
        words_by_page[page_id].append(word)

    # Highlight words on each page
    for page_id, page_words in words_by_page.items():
        page_index = page_id - 1  # convert 1-based → 0-based
        page = pdf_doc[page_index]
        page_height = page.rect.height
        prev_points = None
        for word in page_words:
            points = [
                (word[2], page_height - word[3]),  # top-left
                (word[4], page_height - word[5]),  # top-right
                (word[6], page_height - word[7]),  # bottom-right
                (word[8], page_height - word[9]),  # bottom-left
            ]
            if prev_points is None:
                prev_points = points
                continue

            # coordinate checks
            y_tol, x_tol = 2, 15
            same_top = abs(prev_points[0][1] - points[0][1]) < y_tol
            same_bottom = abs(prev_points[3][1] - points[3][1]) < y_tol
            small_gap = (points[0][0] - prev_points[1][0]) < x_tol
            if same_top and same_bottom and small_gap:
                # merge polygons
                prev_points = [
                    prev_points[0],  # top-left
                    points[1],  # new top-right
                    points[2],  # new bottom-right
                    prev_points[3],  # bottom-left
                ]
            else:
                # draw previous merged polygon
                page.draw_polyline(
                    prev_points, color=rgb_color, fill=rgb_color, fill_opacity=0.3
                )
                prev_points = points

        # draw final merged polygon
        if prev_points is not None:
            page.draw_polyline(
                prev_points, color=rgb_color, fill=rgb_color, fill_opacity=0.3
            )

    # Save highlighted PDF
    output_path = pdf_highlighted_path(paper_id)
    pdf_doc.save(output_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
    pdf_doc.close()

    return output_path
