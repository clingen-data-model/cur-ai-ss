import fitz  # PyMuPDF


def pdf_first_page_to_thumbnail_pymupdf_bytes(
    content: bytes,
    zoom: float = 2.0,
) -> bytes:
    """
    Generate a thumbnail (PNG bytes) of the first page of a PDF from in-memory PDF bytes.

    Args:
        content: Raw PDF bytes.
        zoom: Zoom factor controlling resolution (2.0 ≈ 144 DPI).

    Returns:
        PNG image bytes of the first page.

    Raises:
        ValueError: If the PDF is empty or cannot be rendered.
        RuntimeError: If PyMuPDF fails to process the PDF.
    """
    try:
        with fitz.open(stream=content, filetype='pdf') as doc:
            if doc.page_count == 0:
                raise ValueError('PDF contains no pages')

            page = doc.load_page(0)
            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix)

            # Return PNG bytes
            return pix.tobytes('png')

    except Exception as e:
        raise RuntimeError('Failed to generate PDF thumbnail') from e
