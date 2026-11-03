"""The PDF parsing service: Docling's models run on a GPU elsewhere.

The worker's PDF Parsing step is a Docling run (layout, table structure, OCR)
that takes the CPU-only dev-caa VM minutes per paper and a quarter of an hour
for a long supplement. docling-serve is the Docling project's HTTP server
around the same ``DocumentConverter``; ``infrastructure/terraform/pdf-parsing``
stands one up as the ``pdf-parsing`` Cloud Run service with an NVIDIA L4
that scales to zero between papers. With ``PDF_PARSING_SERVICE_URL`` and
``PDF_PARSING_EXCHANGE_BUCKET`` set, ``parse_content`` has the service
convert the PDF and gets the ``DoclingDocument`` back; everything downstream
of the converter -- cropping tables and figures, the word layout, table
correction, anchoring -- is unchanged and still runs in the worker, on the
document the service returns.

Neither the PDF nor the document travels in an HTTP body. Cloud Run caps
both at 32 MiB, and the document with its figure crops embedded runs to
20 MiB for a figure-heavy paper. The exchange bucket is the medium instead:
the worker puts the PDF in the bucket, hands the service a signed URL to
read it and a signed URL to write to, posts only those and the options
(``/v1/convert/source``), and pulls the bundle the service wrote -- a zip
holding the document's JSON, inside the multipart form envelope docling-
serve's put target uploads with -- back out of the bucket. The two objects
are deleted after the run, and the bucket's one-day lifecycle rule sweeps
any a crash leaves behind.

One thing the service does not send back is rebuilt here: page renders.
Docling keeps a render of every page in the document and crops table images
out of them (``TableItem.get_image``). The service is asked not to include
them (at scale 4 a page is ~20 MB) and the pages that carry a table are
rendered again locally with pypdfium2 at the same scale -- cheap and
model-free; the parsing backend has no random page access -- so the crops
come out as they would from the in-process run (both backends report the
same page geometry). Figures arrive embedded in the document
(``image_export_mode`` embedded), already cropped by the service.

The request options mirror ``parse.convert_locally`` (docling-parse backend,
accurate tables, OCR on, scale 4). The service is docling-serve, whose
release (``infrastructure/pdf-parsing/base-tag``) is kept at the one locking
the docling version pyproject pins, so the service runs the same models,
with the post-processing override in ``lib.misc.pdf.layout`` installed in its
image. See docs/cloud-run-parsing.md.

Calls carry a Google identity token; the Cloud Run service admits only the
IAM members the terraform stack names (the VM's service account, and
operators for testing from a laptop). URLs are signed as the account the
process runs as: the VM's service account on dev-caa, or on a laptop an
application-default login that impersonates it
(``gcloud auth application-default login --impersonate-service-account``).
"""

import asyncio
import io
import logging
import subprocess
import time
import uuid
import zipfile
from datetime import timedelta
from typing import Any, cast

import google.auth
import httpx
import pypdfium2 as pdfium
from docling_core.types.doc import DoclingDocument, ImageRef
from google.auth.transport.requests import Request
from google.cloud.exceptions import NotFound
from google.cloud.storage import Blob, Client

from lib.misc.pdf.paths import IMAGE_RESOLUTION_SCALE

logger = logging.getLogger(__name__)

CONVERT_PATH = '/v1/convert/source'

# What ``convert_locally`` configures the pipeline with: docling-parse backend,
# OCR, accurate table structure, figure crops at the scale tables and figures
# are stored at. Page renders are not sent back (module docstring), and a
# failed page fails the request, as the in-process converter raises.
CONVERT_OPTIONS: dict[str, Any] = {
    'to_formats': ['json'],
    'image_export_mode': 'embedded',
    'include_images': True,
    'include_page_images': False,
    'images_scale': IMAGE_RESOLUTION_SCALE,
    'pdf_backend': 'docling_parse',
    'do_ocr': True,
    'do_table_structure': True,
    'table_mode': 'accurate',
    'abort_on_error': True,
}

# The service holds the request until the conversion is done, up to its
# DOCLING_SERVE_MAX_SYNC_WAIT of five minutes (a 32-page paper took 32 s);
# Cloud Run's request timeout and this one allow a minute more.
TIMEOUT = httpx.Timeout(360.0, connect=60.0)

# The signed URLs outlive the longest request by a wide margin.
URL_LIFETIME = timedelta(minutes=30)

# What the service wrote the result as: a zip holding the document's JSON.
BUNDLE_DOCUMENT = 'content.json'


class RemoteConversionError(RuntimeError):
    """The service did not return a usable document."""


def identity_token(audience: str) -> str:
    """A Google identity token for the service: the VM's service account from
    the GCE metadata server, else the operator's ``gcloud`` login."""
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


def signed_url(blob: Blob, method: str) -> str:
    """A V4 signed URL for one request on the object, signed through the IAM
    signBlob API as the service account the process's credentials carry."""
    credentials, _ = google.auth.default()
    credentials.refresh(Request())
    email = getattr(credentials, 'service_account_email', None) or getattr(
        credentials, 'signer_email', None
    )
    if not email:
        raise RemoteConversionError(
            'the application default credentials carry no service account to '
            'sign URLs as (module docstring)'
        )
    return cast(
        str,
        blob.generate_signed_url(
            version='v4',
            expiration=URL_LIFETIME,
            method=method,
            service_account_email=email,
            access_token=credentials.token,
        ),
    )


def unwrap_multipart(raw: bytes) -> bytes:
    """The one file inside a multipart form body, as docling-serve's put
    target uploads the bundle; bytes that are not such a body are returned
    as they are."""
    if not raw.startswith(b'--'):
        return raw
    boundary = raw.split(b'\r\n', 1)[0]
    start = raw.index(b'\r\n\r\n') + 4
    end = raw.rindex(b'\r\n' + boundary)
    return raw[start:end]


def load_bundle(raw: bytes) -> DoclingDocument:
    """The document from the object the service wrote."""
    payload = unwrap_multipart(raw)
    if payload[:2] == b'PK':
        with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
            if BUNDLE_DOCUMENT not in bundle.namelist():
                raise RemoteConversionError(
                    f'bundle holds {bundle.namelist()}, not {BUNDLE_DOCUMENT}'
                )
            payload = bundle.read(BUNDLE_DOCUMENT)
    return DoclingDocument.model_validate_json(payload)


def attach_page_images(document: DoclingDocument, content: bytes) -> None:
    """Render the pages that carry a table, as Docling's pipeline would have,
    so ``TableItem.get_image`` can crop them. Pages without a table are left
    without a render: nothing downstream crops from them."""
    page_numbers = sorted(
        {table.prov[0].page_no for table in document.tables if table.prov}
    )
    if not page_numbers:
        return
    # pypdfium2 directly rather than through docling's backend class, which
    # would import docling and with it transformers and torch (see parse.py).
    # The render is what that backend does: 1.5x the scale, resized down to
    # the scale, which it finds sharper; the page size is pdfium's, the
    # visible box as displayed.
    pdf = pdfium.PdfDocument(content)
    try:
        for page_no in page_numbers:
            page = document.pages.get(page_no)
            if page is None:
                continue
            pdf_page = pdf[page_no - 1]
            try:
                bitmap = pdf_page.render(scale=IMAGE_RESOLUTION_SCALE * 1.5, rotation=0)
                rendered = bitmap.to_pil().copy()
                bitmap.close()
                rendered = rendered.resize(
                    (
                        round(pdf_page.get_width() * IMAGE_RESOLUTION_SCALE),
                        round(pdf_page.get_height() * IMAGE_RESOLUTION_SCALE),
                    )
                )
            finally:
                pdf_page.close()
            page.image = ImageRef.from_pil(
                rendered, dpi=round(72 * IMAGE_RESOLUTION_SCALE)
            )
    finally:
        pdf.close()


def _delete_quietly(blob: Blob) -> None:
    try:
        blob.delete()
    except NotFound:
        pass


async def convert_pdf_remote(
    content: bytes,
    *,
    base_url: str,
    bucket: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> DoclingDocument:
    """The PDF's ``DoclingDocument`` from the service at ``base_url``, through
    the exchange ``bucket`` (module docstring). Awaiting it keeps the worker's
    loop free for other tasks, which the in-process converter never did.
    ``transport`` is for tests."""
    token = identity_token(base_url)
    started = time.monotonic()
    job = uuid.uuid4().hex
    exchange = Client().bucket(bucket)
    source = exchange.blob(f'{job}/content.pdf')
    result = exchange.blob(f'{job}/result')
    try:
        await asyncio.to_thread(
            source.upload_from_string, content, content_type='application/pdf'
        )
        request = {
            'options': CONVERT_OPTIONS,
            'sources': [
                {
                    'kind': 'http',
                    'url': await asyncio.to_thread(signed_url, source, 'GET'),
                }
            ],
            'target': {
                'kind': 'put',
                'url': await asyncio.to_thread(signed_url, result, 'PUT'),
            },
        }
        async with httpx.AsyncClient(timeout=TIMEOUT, transport=transport) as client:
            response = await client.post(
                base_url.rstrip('/') + CONVERT_PATH,
                headers={'Authorization': f'Bearer {token}'},
                json=request,
            )
        if response.status_code != 200:
            raise RemoteConversionError(
                f'service answered {response.status_code}: {response.text[:500]}'
            )
        summary = response.json()
        if (
            summary.get('num_succeeded', 0) + summary.get('num_partially_succeeded', 0)
            != 1
        ):
            raise RemoteConversionError(f'conversion failed: {summary}')
        if summary.get('num_partially_succeeded'):
            logger.warning('converted with failed pages: %s', summary)
        try:
            raw = await asyncio.to_thread(result.download_as_bytes)
        except NotFound as exc:
            raise RemoteConversionError('the service wrote no bundle') from exc
    finally:
        await asyncio.to_thread(_delete_quietly, source)
        await asyncio.to_thread(_delete_quietly, result)
    document = load_bundle(raw)
    logger.info(
        'service converted %d bytes in %.1fs (server time %s, bundle %d bytes)',
        len(content),
        time.monotonic() - started,
        summary.get('processing_time'),
        len(raw),
    )
    attach_page_images(document, content)
    return document
