import io

import fitz  # PyMuPDF


def merge_pdfs(main_pdf_bytes: bytes, supplement_pdf_bytes: bytes) -> bytes:
    """
    Merge two PDFs into one, with the main PDF first followed by the supplement.

    Args:
        main_pdf_bytes: The main PDF content as bytes
        supplement_pdf_bytes: The supplement PDF content as bytes

    Returns:
        The merged PDF as bytes
    """
    # Open PDFs from bytes
    main_doc = fitz.open(stream=io.BytesIO(main_pdf_bytes), filetype='pdf')
    supplement_doc = fitz.open(stream=io.BytesIO(supplement_pdf_bytes), filetype='pdf')

    try:
        # Insert all pages from supplement into main document
        main_doc.insert_pdf(supplement_doc)

        # Write merged PDF to bytes
        output = io.BytesIO()
        main_doc.save(output)
        return output.getvalue()
    finally:
        main_doc.close()
        supplement_doc.close()


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
