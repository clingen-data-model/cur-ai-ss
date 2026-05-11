import io
from pathlib import Path
from typing import TYPE_CHECKING

from pptx import Presentation
from pptx.util import Inches, Pt

from lib.misc.curation.models import CurationSummaryRow, SectionContent

if TYPE_CHECKING:
    from pptx.text.text import TextFrame


def _format_cell_with_sections(
    text_frame: 'TextFrame', sections: list[SectionContent]
) -> None:
    """Format a cell with bold section titles and paragraph breaks."""
    text_frame.clear()

    for idx, section in enumerate(sections):
        p = text_frame.add_paragraph()

        title_run = p.add_run()
        title_run.text = section.title
        title_run.font.bold = True

        if section.content:
            content_run = p.add_run()
            content_run.text = '\n' + section.content

        if idx < len(sections) - 1:
            text_frame.add_paragraph()


def build_curation_pptx(rows: list[CurationSummaryRow]) -> bytes:
    """Generate a PPTX slide with curation summary table.

    Creates a single landscape slide with a table containing:
    - Header row: Publication & Testing | Proband | Variant Info | Clinical Presentation | Functional/Segregation | Score
    - One data row per CurationSummaryRow
    - Optional pedigree image if available

    Returns raw PPTX bytes.
    """
    prs = Presentation()
    prs.slide_width = Inches(13)
    prs.slide_height = Inches(7.5)

    # Add blank slide layout
    blank_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank_layout)

    # Table dimensions: (rows + 1 header) x 6 columns
    rows_count = len(rows) + 1  # +1 for header
    cols_count = 6

    # Add table shape
    left = Inches(0.5)
    top = Inches(0.5)
    width = Inches(12)
    height = Inches(6.5)

    table_shape = slide.shapes.add_table(
        rows_count, cols_count, left, top, width, height
    )
    table = table_shape.table

    # Set column widths
    col_width = int(width / cols_count)
    for col_idx in range(cols_count):
        table.columns[col_idx].width = col_width

    # Header row - set smaller height
    header_row = table.rows[0]
    header_row.height = Inches(0.4)

    headers = [
        'Publication & Testing',
        'Proband',
        'Variant Info',
        'Clinical Presentation',
        'Functional/Segregation',
        'Score',
    ]
    for col_idx, header_text in enumerate(headers):
        cell = table.cell(0, col_idx)
        cell.text = header_text
        # Format header
        text_frame = cell.text_frame
        text_frame.word_wrap = True
        for paragraph in text_frame.paragraphs:
            for run in paragraph.runs:
                run.font.bold = True
                run.font.size = Pt(9)

    # Data rows
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
            cell = table.cell(row_idx, col_idx)
            text_frame = cell.text_frame
            text_frame.word_wrap = True

            # Format with sections
            _format_cell_with_sections(text_frame, sections)

            # Set font size for all text
            for paragraph in text_frame.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(8)

    # Add pedigree image if available (bottom third of first column)
    for row_data in rows:
        if row_data.pedigree_image_path:
            image_path = Path(row_data.pedigree_image_path)
            if image_path.exists():
                slide.shapes.add_picture(
                    str(image_path), Inches(0.5), Inches(5), width=Inches(2)
                )

    pptx_bytes_io = io.BytesIO()
    prs.save(pptx_bytes_io)
    return pptx_bytes_io.getvalue()
