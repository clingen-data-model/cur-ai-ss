import io
import json
import zipfile
from typing import Any
from unittest.mock import AsyncMock

import fitz
import httpx
import pytest
from docling_core.types.doc import (
    BoundingBox,
    CoordOrigin,
    DoclingDocument,
    ImageRef,
    ProvenanceItem,
    Size,
    TableData,
)
from google.cloud.exceptions import NotFound
from PIL import Image

from lib.misc.pdf import parse, remote
from lib.misc.pdf.parse import parse_content
from lib.misc.pdf.paths import (
    IMAGE_RESOLUTION_SCALE,
    document_image_path,
    document_raw_path,
    document_success_path,
    document_table_image_path,
    document_words_json_path,
)
from lib.misc.pdf.remote import (
    CONVERT_OPTIONS,
    RemoteConversionError,
    convert_pdf_remote,
    unwrap_multipart,
)

BASE_URL = 'https://pdf-parsing.test'
BUCKET = 'exchange-test'


def _document(page_size: Size) -> DoclingDocument:
    """A one-page document with a table and an embedded picture on it, as
    the service returns one: provenance for both, image for the picture only."""
    doc = DoclingDocument(name='content')
    doc.add_page(page_no=1, size=page_size)
    prov = ProvenanceItem(
        page_no=1,
        bbox=BoundingBox(
            l=72, t=700, r=540, b=580, coord_origin=CoordOrigin.BOTTOMLEFT
        ),
        charspan=(0, 0),
    )
    doc.add_table(data=TableData(num_rows=0, num_cols=0, table_cells=[]), prov=prov)
    picture = Image.new('RGB', (10, 10), 'red')
    doc.add_picture(image=ImageRef.from_pil(picture, dpi=72), prov=prov)
    return doc


def _bundle(document: DoclingDocument) -> bytes:
    """The object docling-serve's put target writes: a zip of the document's
    JSON, inside a multipart form body."""
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('content.json', document.model_dump_json())
    boundary = b'--abc123'
    return b'\r\n'.join(
        [
            boundary,
            b'Content-Disposition: form-data; name="file"; '
            b'filename="converted_docs.zip"',
            b'Content-Type: application/zip',
            b'',
            archive.getvalue(),
            boundary + b'--',
            b'',
        ]
    )


class FakeBlob:
    def __init__(self, store: 'FakeStore', name: str) -> None:
        self.store = store
        self.name = name

    def upload_from_string(self, data: bytes, content_type: str) -> None:
        self.store.objects[self.name] = data

    def download_as_bytes(self) -> bytes:
        if self.name not in self.store.objects:
            raise NotFound(self.name)
        return self.store.objects[self.name]

    def delete(self) -> None:
        if self.name not in self.store.objects:
            raise NotFound(self.name)
        del self.store.objects[self.name]
        self.store.deleted.append(self.name)


class FakeStore:
    """The exchange bucket: objects by name, and what the service will have
    written under a job's ``result`` once it is asked to convert."""

    def __init__(self, result: bytes | None) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.result = result

    def blob(self, name: str) -> FakeBlob:
        return FakeBlob(self, name)

    def bucket(self, name: str) -> 'FakeStore':
        assert name == BUCKET
        return self


def _serve(
    store: FakeStore, summary: dict[str, Any] | None = None
) -> httpx.MockTransport:
    """The service: records the request, writes the bundle under the job the
    signed target URL names, answers with the run's summary."""

    def handler(request: httpx.Request) -> httpx.Response:
        handler.requests.append(request)  # type: ignore[attr-defined]
        body = json.loads(request.content)
        target = body['target']['url']
        job = target.removeprefix('https://signed/').split('/')[0]
        if store.result is not None:
            store.objects[f'{job}/result'] = store.result
        return httpx.Response(
            200,
            json=summary
            or {
                'num_converted': 1,
                'num_succeeded': 1,
                'num_partially_succeeded': 0,
                'num_failed': 0,
                'processing_time': 1.5,
            },
        )

    handler.requests = []  # type: ignore[attr-defined]
    return httpx.MockTransport(handler)


@pytest.fixture
def pdf(test_file_contents):
    return test_file_contents('ACN3-7-1962.pdf', mode='rb')


@pytest.fixture
def page_size(pdf):
    rect = fitz.open(stream=pdf, filetype='pdf').load_page(0).rect
    return Size(width=rect.width, height=rect.height)


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setattr(remote, 'identity_token', lambda audience: 'tok')
    monkeypatch.setattr(
        remote,
        'signed_url',
        lambda blob, method: f'https://signed/{blob.name}?{method}',
    )


def _exchange(monkeypatch, result: bytes | None) -> FakeStore:
    store = FakeStore(result)
    monkeypatch.setattr(remote, 'Client', lambda: store)
    return store


async def test_convert_pdf_remote_exchanges_through_the_bucket(
    token, monkeypatch, pdf, page_size
):
    store = _exchange(monkeypatch, _bundle(_document(page_size)))
    transport = _serve(store)

    document = await convert_pdf_remote(
        pdf, base_url=BASE_URL, bucket=BUCKET, transport=transport
    )

    # One small JSON request: the options, a signed URL to read the PDF the
    # worker uploaded, a signed URL for the service to write the bundle to.
    [request] = transport.handler.requests
    assert request.url == f'{BASE_URL}/v1/convert/source'
    assert request.headers['Authorization'] == 'Bearer tok'
    assert len(request.content) < 2000
    body = json.loads(request.content)
    assert body['options'] == CONVERT_OPTIONS
    [source] = body['sources']
    assert source['kind'] == 'http'
    assert source['url'].startswith('https://signed/')
    assert source['url'].endswith('/content.pdf?GET')
    assert body['target']['kind'] == 'put'
    assert body['target']['url'].endswith('/result?PUT')

    # Both objects are gone afterwards.
    assert store.objects == {}
    assert sorted(name.rsplit('/', 1)[1] for name in store.deleted) == [
        'content.pdf',
        'result',
    ]

    # The table's page was rendered at the stored scale, so the crop
    # Docling's own pipeline would make is available; the picture came
    # embedded and needs no render.
    page = document.pages[1]
    assert page.image is not None
    assert page.image.size.width == round(page_size.width * IMAGE_RESOLUTION_SCALE)
    table_image = document.tables[0].get_image(document)
    assert table_image is not None
    assert table_image.size == (468 * 4, 120 * 4)
    assert document.pictures[0].get_image(document).size == (10, 10)


async def test_convert_pdf_remote_rejects_a_failed_conversion(
    token, monkeypatch, pdf, page_size
):
    store = _exchange(monkeypatch, None)
    transport = _serve(
        store, summary={'num_converted': 1, 'num_succeeded': 0, 'num_failed': 1}
    )
    with pytest.raises(RemoteConversionError, match='num_failed'):
        await convert_pdf_remote(
            pdf, base_url=BASE_URL, bucket=BUCKET, transport=transport
        )
    assert store.objects == {}


async def test_convert_pdf_remote_rejects_a_missing_bundle(
    token, monkeypatch, pdf, page_size
):
    store = _exchange(monkeypatch, None)
    with pytest.raises(RemoteConversionError, match='no bundle'):
        await convert_pdf_remote(
            pdf, base_url=BASE_URL, bucket=BUCKET, transport=_serve(store)
        )
    assert store.objects == {}


async def test_convert_pdf_remote_rejects_an_http_error(token, monkeypatch, pdf):
    store = _exchange(monkeypatch, None)
    transport = httpx.MockTransport(lambda request: httpx.Response(503, text='cold'))
    with pytest.raises(RemoteConversionError, match='503'):
        await convert_pdf_remote(
            pdf, base_url=BASE_URL, bucket=BUCKET, transport=transport
        )
    assert store.objects == {}


def test_unwrap_multipart_returns_the_one_file():
    assert unwrap_multipart(_bundle(DoclingDocument(name='x'))).startswith(b'PK')
    assert unwrap_multipart(b'PK plain') == b'PK plain'


def test_convert_options_mirror_the_local_pipeline():
    assert CONVERT_OPTIONS['pdf_backend'] == 'docling_parse'
    assert CONVERT_OPTIONS['table_mode'] == 'accurate'
    assert CONVERT_OPTIONS['to_formats'] == ['json']
    assert CONVERT_OPTIONS['image_export_mode'] == 'embedded'
    assert CONVERT_OPTIONS['include_page_images'] is False
    assert CONVERT_OPTIONS['images_scale'] == IMAGE_RESOLUTION_SCALE


async def test_parse_content_sends_the_pdf_to_the_service_when_configured(
    mocked_root_dir, monkeypatch, pdf, page_size
):
    monkeypatch.setattr(parse.env, 'PDF_PARSING_SERVICE_URL', BASE_URL)
    monkeypatch.setattr(parse.env, 'PDF_PARSING_EXCHANGE_BUCKET', BUCKET)
    document = _document(page_size)
    parse.attach_page_images(document, pdf)
    remote_convert = AsyncMock(return_value=document)
    monkeypatch.setattr(parse, 'convert_pdf_remote', remote_convert)
    monkeypatch.setattr(parse, 'correct_tables', AsyncMock())

    paper_id = 7
    document_raw_path(paper_id).parent.mkdir(parents=True)
    document_raw_path(paper_id).write_bytes(pdf)
    await parse_content(paper_id, force=True)

    remote_convert.assert_awaited_once()
    assert remote_convert.await_args.kwargs == {'base_url': BASE_URL, 'bucket': BUCKET}
    assert document_success_path(paper_id).exists()
    assert document_table_image_path(paper_id, 0).exists()
    assert document_image_path(paper_id, 0).exists()
    assert len(json.loads(document_words_json_path(paper_id).read_text())) > 100
