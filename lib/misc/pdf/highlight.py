import math
import re
from pathlib import Path
from typing import Any, cast

import fitz
from pydantic import BaseModel
from rapidfuzz import fuzz

from lib.misc.pdf.parse import WordLoc
from lib.misc.pdf.paths import pdf_highlighted_path, pdf_raw_path


class GrobidAnnotation(BaseModel):
    """GROBID-style coordinate with top-left origin (y increases downward)."""

    page: int
    x: float
    y: float
    width: float
    height: float
    color: str
    border: str = 'solid'


def words_to_grobid_annotations(
    words: list[WordLoc],
    page_heights: dict[int, float],
    color: str = 'red',
    border: str = 'solid',
) -> list[GrobidAnnotation]:
    """
    Convert matched WordLoc objects to GROBID-style annotations.

    Creates one annotation per word with top-left origin coordinates.

    Args:
        words: List of WordLoc objects from find_best_match
        page_heights: Dictionary mapping page_idx to page height
        color: Highlight color (default: 'red')
        border: Border style (default: 'solid')

    Returns:
        List of GrobidAnnotation objects, one per word
    """
    annotations = []
    for word in words:
        page_idx = int(word.page_idx)
        page_height = page_heights.get(page_idx, 0)

        # Convert to screen coordinates (top-left origin)
        x = word.x0
        y = page_height - word.y0
        width = word.x1 - word.x0  # top-right - top-left
        height = word.y2 - word.y1  # bottom-right - top-right

        annotations.append(
            GrobidAnnotation(
                page=page_idx,
                x=x,
                y=y,
                width=width,
                height=height,
                color=color,
                border=border,
            )
        )

    return annotations


def get_page_heights(paper_id: str) -> dict[int, float]:
    """
    Get the height of each page in a PDF.

    Args:
        paper_id: The paper ID to identify the PDF file

    Returns:
        Dictionary mapping 1-based page index to height
    """
    pdf_doc = fitz.open(pdf_raw_path(paper_id))
    page_heights = {i + 1: pdf_doc[i].rect.height for i in range(len(pdf_doc))}
    pdf_doc.close()
    return page_heights


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


def find_best_match(query: str, words: list[WordLoc]) -> list[WordLoc] | None:
    """
    Finds the best match of a query in a PDF word list.
    Supports <SPLIT> for evidence spanning multiple pages/sections.

    Args:
        query: The text to search for, with optional <SPLIT> separators
        words: List of WordLoc entries from PDF extraction
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
        token = re.sub(r'\s+', ' ', token)
        return token

    n = len(words)
    normalized_words = [normalize(w.word) for w in words]
    normalized_parts = [normalize(p.strip()) for p in query.split('<SPLIT>')]
    if not normalized_parts:
        return None

    full_span = []
    search_start = 0

    for normalized_part in normalized_parts:
        q_len = len(normalized_part.split())
        min_len, max_len = max(1, q_len - window_size), q_len + window_size
        best_score, best_span = float(0), None

        # Slide window over remaining words
        for i in range(search_start, n):
            for span_len in range(min_len, max_len + 1):
                j = i + span_len
                if j > n:
                    break
                span_text = ' '.join(normalized_words[i:j])
                score = fuzz.ratio(span_text, normalized_part)
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
    words: list[WordLoc],
    rgb_color: tuple[float, float, float],
) -> Path:
    """
    Highlight words in a PDF at their bounding box locations.

    Args:
        paper_id: The paper ID to identify the PDF file
        words: List of WordLoc entries from PDF extraction
        rgb_color: RGB tuple with values 0-1

    Returns:
        Path to the highlighted PDF file
    """

    # Load PDF
    pdf_path = pdf_highlighted_path(paper_id)
    pdf_doc = fitz.open(pdf_path)

    # Group words by page
    words_by_page: dict[int, list[WordLoc]] = {}
    for word in words:
        page_idx = int(word.page_idx)
        if page_idx not in words_by_page:
            words_by_page[page_idx] = []
        words_by_page[page_idx].append(word)

    # Highlight words on each page
    for page_idx, page_words in words_by_page.items():
        page = pdf_doc[page_idx - 1]  # convert 1-based → 0-based
        page_height = page.rect.height
        prev_points = None
        for word in page_words:
            points = [
                (word.x0, page_height - word.y0),  # top-left
                (word.x1, page_height - word.y1),  # top-right
                (word.x2, page_height - word.y2),  # bottom-right
                (word.x3, page_height - word.y3),  # bottom-left
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
