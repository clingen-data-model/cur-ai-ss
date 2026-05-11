from pptx import Presentation
from pptx.util import Inches, Pt

from lib.models.curation_summary import CurationSummaryRow


def build_curation_pptx(rows: list[CurationSummaryRow]) -> bytes:
    """Generate a PPTX slide with curation summary table.

    Creates a single landscape slide with a table containing:
    - Header row: Publication & Testing | Proband | Variant Info | Clinical Presentation | Functional/Segregation | Score
    - One data row per CurationSummaryRow

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
    col_width = width / cols_count
    for col_idx in range(cols_count):
        table.columns[col_idx].width = col_width

    # Header row
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
                run.font.size = Pt(10)

    # Data rows
    for row_idx, row_data in enumerate(rows, start=1):
        cell_values = [
            row_data.publication_and_testing,
            row_data.proband,
            row_data.variant_info,
            row_data.clinical_presentation,
            row_data.functional_segregation,
            row_data.score,
        ]
        for col_idx, cell_text in enumerate(cell_values):
            cell = table.cell(row_idx, col_idx)
            cell.text = cell_text
            # Format data cells
            text_frame = cell.text_frame
            text_frame.word_wrap = True
            for paragraph in text_frame.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(9)

    # Save to bytes
    import io

    pptx_bytes_io = io.BytesIO()
    prs.save(pptx_bytes_io)
    return pptx_bytes_io.getvalue()
