import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, cast

import fitz
from pydantic import BaseModel
from rapidfuzz import fuzz

from lib.misc.pdf.parse import Polygon, WordLoc
from lib.misc.pdf.paths import pdf_highlighted_path, pdf_raw_path

from Bio.Align import PairwiseAligner


class GrobidAnnotation(BaseModel):
    """GROBID-style coordinate with top-left origin (y increases downward)."""

    page: int
    x: float
    y: float
    width: float
    height: float
    color: str
    border: str = 'solid'


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


def merge_adjacent_polygons(
    words: list[WordLoc],
) -> list[Polygon]:
    """
    Merge adjacent polygons if they are aligned and close together.

    Args:
        words: List of WordLoc objects (each with 4 corner coordinates)

    Returns:
        List of merged Polygon objects
    """
    if not words:
        return []

    y_tol, x_tol = 2, 15
    merged: list[Polygon] = [words[0].to_polygon()]

    for word in words[1:]:
        prev = merged[-1]
        same_top = abs(prev.y0 - word.y0) < y_tol
        same_bottom = abs(prev.y3 - word.y3) < y_tol
        small_gap = (word.x0 - prev.x1) < x_tol

        if same_top and same_bottom and small_gap:
            # Merge: extend previous polygon's right edge to current word's right edge
            merged[-1] = Polygon(
                x0=prev.x0,
                y0=prev.y0,
                x1=word.x1,
                y1=word.y1,
                x2=word.x2,
                y2=word.y2,
                x3=prev.x3,
                y3=prev.y3,
            )
        else:
            # Add as separate polygon
            merged.append(word.to_polygon())

    return merged


def find_best_match(query: str, words: list[WordLoc]) -> list[WordLoc] | None:
    def get_aligner() -> PairwiseAligner:
        aligner = PairwiseAligner()
        aligner.mode = 'local'  # Smith-Waterman local alignment
        aligner.match_score = 1.0  # Match/mismatch scoring
        aligner.mismatch_score = -0.5  # Affine Gap penalties
        aligner.open_gap_score = (
            -2.5
        )  # Larger Penalty to open a gap (allowing a single large page break)
        aligner.extend_gap_score = -0.1  # Smaller Penalty to extend a gap
        return aligner

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

    def get_word_to_offset(normalized_words: list[str]) -> list[tuple[int, int]]:
        offsets = []
        start = 0
        for normalized_word in normalized_words:
            end = start + len(normalized_word)
            offsets.append((start, end))
            start = end + 1
        return offsets

    def get_words_from_alignment(
        aligned_blocks: list[tuple[int, int]],
        word_to_offset: list[tuple[int, int]],
        words: list[WordLoc],
    ) -> list[WordLoc]:
        matched_words = []
        for pdf_start, pdf_end in aligned_blocks:
            for i, (start, end) in enumerate(word_to_offset):
                if end > pdf_start and start < pdf_end:
                    matched_words.append(words[i])
        return matched_words

    n_words, n_query = len(words), len(query.split())
    if n_words == 0 or n_query == 0:
        return None

    normalized_query = normalize(query)
    normalized_words = [normalize(w.word) for w in words]
    word_to_offset = get_word_to_offset(normalized_words)
    aligner = get_aligner()
    alignments = aligner.align(normalized_query, ' '.join(normalized_words))
    if not alignments:
        return None
    return get_words_from_alignment(alignments[0].aligned[1], word_to_offset, words)


def words_to_grobid_annotations(
    paper_id: str,
    words: list[WordLoc],
    color: tuple[float, float, float],
) -> list[GrobidAnnotation]:
    pdf_path = pdf_highlighted_path(paper_id)
    pdf_doc = fitz.open(pdf_path)

    words_by_page: dict[int, list[WordLoc]] = defaultdict(list)
    for word in words:
        words_by_page[int(word.page_idx)].append(word)

    annotations = []
    for page_idx, page_words in words_by_page.items():
        page = pdf_doc[page_idx - 1]  # convert 1-based → 0-based
        page_height = page.rect.height

        # Merge adjacent words on this page into polygons
        merged_polygons = merge_adjacent_polygons(page_words)

        for polygon in merged_polygons:
            # Convert to screen coordinates (bottom-left origin, using bottom-left point)
            x = polygon.x3
            y = page_height - polygon.y3
            width = polygon.x1 - polygon.x0
            height = polygon.y2 - polygon.y1

            annotations.append(
                GrobidAnnotation(
                    page=page_idx,
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    color=f'rgb({color[0] * 255.0},{color[1] * 255.0},{color[2] * 255.0})',
                    border='solid',
                )
            )

    pdf_doc.close()

    return annotations


def highlight_words_in_pdf(
    paper_id: str,
    words: list[WordLoc],
    rgb_color: tuple[float, float, float],
) -> Path:
    # Load PDF
    pdf_path = pdf_highlighted_path(paper_id)
    pdf_doc = fitz.open(pdf_path)

    # Group words by page
    words_by_page: dict[int, list[WordLoc]] = defaultdict(list)
    for word in words:
        words_by_page[int(word.page_idx)].append(word)

    # Highlight words on each page
    for page_idx, page_words in words_by_page.items():
        page = pdf_doc[page_idx - 1]  # convert 1-based → 0-based
        page_height = page.rect.height

        # Merge adjacent polygons
        merged_polygons = merge_adjacent_polygons(page_words)

        # Draw all merged polygons
        for polygon in merged_polygons:
            points = [
                (polygon.x0, page_height - polygon.y0),
                (polygon.x1, page_height - polygon.y1),
                (polygon.x2, page_height - polygon.y2),
                (polygon.x3, page_height - polygon.y3),
            ]
            page.draw_polyline(
                points, color=rgb_color, fill=rgb_color, fill_opacity=0.3
            )

    # Save highlighted PDF
    output_path = pdf_highlighted_path(paper_id)
    pdf_doc.save(output_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
    pdf_doc.close()

    return output_path
