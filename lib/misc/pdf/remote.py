"""The PDF parsing service: Docling's models run on a GPU elsewhere.

The worker's PDF Parsing step is a Docling run (layout, table structure, OCR)
that takes the CPU-only dev-caa VM minutes per paper and a quarter of an hour
for a long supplement. docling-serve is the Docling project's HTTP server
around the same ``DocumentConverter``; ``infrastructure/terraform/pdf-parsing``
stands one up as the ``pdf-parsing`` Cloud Run service with an NVIDIA L4
that scales to zero between papers. With ``PDF_PARSING_SERVICE_URL`` set,
``parse_content`` sends the PDF there and gets the ``DoclingDocument`` back; everything downstream of the
converter -- cropping tables and figures, the word layout, table correction,
anchoring -- is unchanged and still runs in the worker, on the document the
server returns.

One thing the server does not send back is rebuilt here: page renders.
Docling keeps a render of every page in the document and crops table images
out of them (``TableItem.get_image``). The server is asked not to send them
(``include_page_images`` off: at scale 4 a page is ~20 MB) and the pages that
carry a table are rendered again locally with the same backend (pypdfium2)
at the same scale -- cheap and model-free -- so the crops come out as they
would from the in-process run. Figures arrive embedded in the document
(``image_export_mode`` embedded), already cropped by the server.

The request options mirror ``parse.convert_locally`` (pypdfium2 backend,
accurate tables, OCR on, scale 4), and the pinned docling-serve release
bundles the docling version pyproject pins, so the server runs the same
models. The one known difference: it runs stock Docling, without the
post-processing override in ``lib.misc.pdf.layout`` that keeps a multi-panel
figure whole. See docs/cloud-run-parsing.md.

Calls carry a Google identity token; the Cloud Run service admits only the
IAM members the terraform stack names (the VM's service account, and
operators for testing from a laptop).
"""

import logging
import os
import subprocess
import time
from io import BytesIO
from typing import cast

import httpx
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.base_models import InputFormat
from docling.datamodel.document import InputDocument
from docling_core.types.doc import DoclingDocument, ImageRef

logger = logging.getLogger(__name__)

CONVERT_PATH = '/v1/convert/file'

# Statuses docling's own ``DocumentConverter.convert`` returns a document for
# rather than raising (``ConversionStatus``): a partial success is a document
# with some pages failed, which the errors list names.
ACCEPTED_STATUSES = ('success', 'partial_success')


class RemoteConversionError(RuntimeError):
    """docling-serve did not return a usable document."""


def convert_options(images_scale: float) -> dict[str, str]:
    """The form fields of a conversion request, as ``convert_locally`` would
    configure the pipeline: pypdfium2 backend, OCR, accurate table structure,
    figure crops at ``images_scale``; page renders are not sent back (see the
    module docstring). ``abort_on_error`` makes a failed page fail the request,
    as the in-process converter raises."""
    return {
        'to_formats': 'json',
        'image_export_mode': 'embedded',
        'include_images': 'true',
        'include_page_images': 'false',
        'images_scale': str(images_scale),
        'pdf_backend': 'pypdfium2',
        'do_ocr': 'true',
        'do_table_structure': 'true',
        'table_mode': 'accurate',
        'abort_on_error': 'true',
    }


def identity_token(audience: str) -> str:
    """A Google identity token for the service: ``PDF_PARSING_ID_TOKEN`` if
    set (tests, or a token minted by hand), else the VM's service account from
    the GCE metadata server, else the operator's ``gcloud`` login."""
    if token := os.environ.get('PDF_PARSING_ID_TOKEN'):
        return token
    try:
        response = httpx.get(
            'http://metadata.google.internal/computeMetadata/v1/instance/'
            'service-accounts/default/identity',
            params={'audience': audience, 'format': 'full'},
            headers={'Metadata-Flavor': 'Google'},
            timeout=2.0,
        )
        if response.status_code == 200:
            return response.text
    except httpx.HTTPError:
        pass
    result = subprocess.run(
        ['gcloud', 'auth', 'print-identity-token'],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def attach_page_images(
    document: DoclingDocument, content: bytes, images_scale: float
) -> None:
    """Render the pages that carry a table, as Docling's pipeline would have,
    so ``TableItem.get_image`` can crop them. Pages without a table are left
    without a render: nothing downstream crops from them."""
    page_numbers = sorted(
        {table.prov[0].page_no for table in document.tables if table.prov}
    )
    if not page_numbers:
        return
    in_doc = InputDocument(
        path_or_stream=BytesIO(content),
        format=InputFormat.PDF,
        backend=PyPdfiumDocumentBackend,
        filename='content.pdf',
    )
    backend = cast(PyPdfiumDocumentBackend, in_doc._backend)
    try:
        for page_no in page_numbers:
            page = document.pages.get(page_no)
            if page is None:
                continue
            rendered = backend.load_page(page_no - 1).get_page_image(scale=images_scale)
            page.image = ImageRef.from_pil(rendered, dpi=round(72 * images_scale))
    finally:
        backend.unload()


async def convert_pdf_remote(
    content: bytes,
    *,
    base_url: str,
    images_scale: float,
    timeout_s: float = 360.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> DoclingDocument:
    """The PDF's ``DoclingDocument`` from docling-serve at ``base_url``.

    One synchronous request: the service holds it until the conversion is
    done, up to its ``DOCLING_SERVE_MAX_SYNC_WAIT`` of five minutes (a
    32-page paper took 32 s); Cloud Run's request timeout and the client's
    allow a minute more. Awaiting it keeps the worker's loop free for other
    tasks, which the in-process converter never did.
    """
    url = base_url.rstrip('/') + CONVERT_PATH
    token = identity_token(base_url)
    started = time.monotonic()
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_s, connect=60.0), transport=transport
    ) as client:
        response = await client.post(
            url,
            headers={'Authorization': f'Bearer {token}'},
            data=convert_options(images_scale),
            files={'files': ('content.pdf', content, 'application/pdf')},
        )
    if response.status_code != 200:
        raise RemoteConversionError(
            f'docling-serve answered {response.status_code}: {response.text[:500]}'
        )
    body = response.json()
    status = body.get('status')
    errors = body.get('errors') or []
    if status not in ACCEPTED_STATUSES:
        raise RemoteConversionError(f'conversion status {status!r}: {errors}')
    if errors:
        logger.warning('docling-serve converted with errors: %s', errors)
    json_content = (body.get('document') or {}).get('json_content')
    if not json_content:
        raise RemoteConversionError('response carries no json_content')
    logger.info(
        'docling-serve converted %d bytes in %.1fs (server time %s)',
        len(content),
        time.monotonic() - started,
        body.get('processing_time'),
    )
    document = DoclingDocument.model_validate(json_content)
    attach_page_images(document, content, images_scale)
    return document
