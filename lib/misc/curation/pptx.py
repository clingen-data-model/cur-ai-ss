import io
from pathlib import Path
from typing import TYPE_CHECKING

from pptx import Presentation
from pptx.util import Inches, Pt

from lib.misc.curation.models import CurationSummaryRow, SectionContent

if TYPE_CHECKING:
    from pptx.presentation import Presentation as PresentationDoc
    from pptx.text.text import TextFrame

# python-pptx API Guide:
# - Inches(n): Converts inches to EMUs (English Metric Units). PowerPoint uses EMUs internally.
#   1 inch = 914,400 EMUs. Inches() is a convenience function for human-readable measurements.
# - Pt(n): Converts points to EMUs for font sizes. 1 point ≈ 12,700 EMUs.
# - Presentation(): Creates a new presentation object (in-memory, 16:9 aspect by default)
# - prs.slide_width/slide_height: Set slide dimensions in EMUs
# - prs.slide_layouts[i]: Accesses predefined layouts (11 total, 0-10):
#   0=Title Slide, 1=Title and Content, 2=Section Header, 3=Two Content, 4=Comparison,
#   5=Title Only, 6=Blank, 7=Content with Caption, 8=Picture with Caption,
#   9=Title and Vertical Text, 10=Vertical Title and Text
# - slide.shapes: Container for all objects on a slide (tables, text boxes, images, etc.)
# - TextFrame: Represents text within a shape; allows adding paragraphs and formatting


def _format_cell_with_sections(
    text_frame: 'TextFrame', sections: list[SectionContent]
) -> None:
    """Format a cell with bold section titles and paragraph breaks.

    Uses the TextFrame API to add paragraphs and runs with different formatting.
    Demonstrates:
    - text_frame.clear(): Removes all existing paragraphs
    - text_frame.add_paragraph(): Adds a new paragraph (equivalent to pressing Enter)
    - paragraph.add_run(): Adds a run (contiguous text with same formatting)
    - run.font properties: Modify character-level formatting (bold, size, color, etc.)
    """
    # Clear existing content from the text frame. This ensures we start fresh.
    text_frame.clear()

    for idx, section in enumerate(sections):
        # Add a new paragraph to the text frame. Paragraphs represent logical text blocks.
        # Each paragraph has independent line spacing, alignment, indentation properties.
        p = text_frame.add_paragraph()

        # Add a run for the section title. A run is the smallest unit of consistent formatting.
        # Multiple runs within the same paragraph can have different formatting.
        title_run = p.add_run()
        title_run.text = section.title
        # Make the title bold using the font property of the run.
        title_run.font.bold = True

        # Add the content text if present. Prefix with newline for visual separation.
        if section.content:
            # Add a second run to the same paragraph for the content (different formatting).
            content_run = p.add_run()
            content_run.text = '\n' + section.content

        # Add a blank paragraph between sections for visual spacing (except after the last section).
        if idx < len(sections) - 1:
            text_frame.add_paragraph()


# Columns whose content is the proband's, not the variant's: on a slide with
# several variant rows they are merged into one cell down the slide.
_PROBAND_COLUMNS = (0, 1, 3, 5)

_HEADERS = [
    'Publication & Testing',
    'Proband',
    'Variant Info',
    'Clinical Presentation',
    'Functional/Segregation',
    'Score',
]

_SLIDE_WIDTH = Inches(13)
_SLIDE_HEIGHT = Inches(7.5)
_MARGIN = Inches(0.5)
_TABLE_WIDTH = Inches(12)
# The table's nominal height; PowerPoint grows the rows past it when their
# text needs more room. It ends above the pedigree.
_TABLE_HEIGHT = Inches(4.3)
_PEDIGREE_TOP = Inches(5)
_PEDIGREE_WIDTH = Inches(2)
_PEDIGREE_MAX_HEIGHT = Inches(2.2)


def _slides_by_proband(
    rows: list[CurationSummaryRow],
) -> list[list[CurationSummaryRow]]:
    """The rows of each proband, in the order the probands first appear."""
    groups: dict[int, list[CurationSummaryRow]] = {}
    for row in rows:
        groups.setdefault(row.patient_id, []).append(row)
    return list(groups.values())


def _add_proband_slide(prs: 'PresentationDoc', rows: list[CurationSummaryRow]) -> None:
    """One slide: the header row, then one row per variant of the proband."""
    # Retrieve the Blank layout (index 6) to avoid default title/content placeholders.
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    rows_count = len(rows) + 1  # +1 for header
    cols_count = len(_HEADERS)

    # slide.shapes.add_table(rows, cols, left, top, width, height) returns a
    # GraphicsFrame wrapping the Table object.
    table = slide.shapes.add_table(
        rows_count, cols_count, _MARGIN, _MARGIN, _TABLE_WIDTH, _TABLE_HEIGHT
    ).table

    col_width = int(_TABLE_WIDTH / cols_count)
    for col_idx in range(cols_count):
        table.columns[col_idx].width = col_width

    # Header row - compact so the data rows get the height.
    table.rows[0].height = Inches(0.4)
    for col_idx, header_text in enumerate(_HEADERS):
        cell = table.cell(0, col_idx)
        cell.text = header_text
        cell.text_frame.word_wrap = True
        for paragraph in cell.text_frame.paragraphs:
            for run in paragraph.runs:
                run.font.bold = True
                run.font.size = Pt(9)

    # Merge the proband's own columns down the variant rows. merge() moves the
    # spanned cells' content into the origin, so it happens before any text
    # goes in: only the origin cell is filled below.
    if len(rows) > 1:
        for col_idx in _PROBAND_COLUMNS:
            table.cell(1, col_idx).merge(table.cell(len(rows), col_idx))

    for row_idx, row_data in enumerate(rows, start=1):
        cell_sections = [
            row_data.publication_and_testing,
            row_data.proband,
            row_data.variant_info,
            row_data.clinical_presentation,
            row_data.functional_segregation,
            row_data.score,
        ]
        for col_idx, sections in enumerate(cell_sections):
            if col_idx in _PROBAND_COLUMNS and row_idx > 1:
                continue
            text_frame = table.cell(row_idx, col_idx).text_frame
            text_frame.word_wrap = True
            _format_cell_with_sections(text_frame, sections)
            for paragraph in text_frame.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(8)

    # The pedigree, once per slide, below the table in the first column.
    # add_picture scales the height to the width; a tall pedigree is then
    # shrunk to fit above the bottom margin.
    image_path = rows[0].pedigree_image_path
    if image_path and Path(image_path).exists():
        picture = slide.shapes.add_picture(
            image_path, _MARGIN, _PEDIGREE_TOP, width=_PEDIGREE_WIDTH
        )
        if picture.height > _PEDIGREE_MAX_HEIGHT:
            picture.width = int(picture.width * _PEDIGREE_MAX_HEIGHT / picture.height)
            picture.height = _PEDIGREE_MAX_HEIGHT


def build_curation_pptx(rows: list[CurationSummaryRow]) -> bytes:
    """Generate the curation summary deck: one landscape slide per proband.

    Every slide carries the full header row (Publication & Testing | Proband |
    Variant Info | Clinical Presentation | Functional/Segregation | Score) and
    the publication and testing cell, so each stands on its own and a long
    paper never runs a table off the slide. A proband with several variants
    gets one row per variant on their slide, with the proband's own columns
    merged down the rows.

    Returns raw PPTX bytes.
    """
    # Create an in-memory Presentation object. Each presentation has a default 16:9 aspect ratio.
    prs = Presentation()
    # Slide dimensions in inches (converted to EMUs internally by python-pptx).
    # 13" x 7.5" gives us a landscape layout suitable for wide tables.
    prs.slide_width = _SLIDE_WIDTH
    prs.slide_height = _SLIDE_HEIGHT

    for proband_rows in _slides_by_proband(rows):
        _add_proband_slide(prs, proband_rows)

    # Save the presentation to a BytesIO buffer (in-memory file).
    pptx_bytes_io = io.BytesIO()
    prs.save(pptx_bytes_io)
    return pptx_bytes_io.getvalue()
