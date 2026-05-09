import io
import zipfile
from pathlib import Path

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


def docx_to_markdown(docx_bytes: bytes, images_dir: Path) -> str:
    import mammoth
    from markdownify import markdownify as md

    images_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as docx_zip:
            # DOCX files store media in word/media/
            for name in docx_zip.namelist():
                if name.startswith('word/media/'):
                    image_data = docx_zip.read(name)
                    # Extract just the filename (e.g., image1.png)
                    filename = Path(name).name
                    (images_dir / filename).write_bytes(image_data)
    except (zipfile.BadZipFile, KeyError):
        pass

    result = mammoth.convert_to_html(io.BytesIO(docx_bytes))
    return md(result.value)


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
