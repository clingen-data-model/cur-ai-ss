import json
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
)

BASE_URL = 'https://pdf-parsing.test'


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


def _serve(document: DoclingDocument, status: str = 'success') -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        handler.requests.append(request)  # type: ignore[attr-defined]
        body = {
            'document': {
                'filename': 'content.pdf',
                'json_content': document.export_to_dict(),
            },
            'status': status,
            'processing_time': 1.5,
            'errors': [],
        }
        return httpx.Response(200, json=body)

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


async def test_convert_pdf_remote_posts_the_pdf_and_renders_table_pages(
    token, pdf, page_size
):
    transport = _serve(_document(page_size))

    document = await convert_pdf_remote(pdf, base_url=BASE_URL, transport=transport)

    [request] = transport.handler.requests
    assert request.url == f'{BASE_URL}/v1/convert/file'
    assert request.headers['Authorization'] == 'Bearer tok'
    assert b'name="pdf_backend"\r\n\r\npypdfium2' in request.content
    assert b'name="images_scale"\r\n\r\n4.0' in request.content
    assert b'filename="content.pdf"' in request.content

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


async def test_convert_pdf_remote_rejects_a_failed_conversion(token, pdf, page_size):
    transport = _serve(_document(page_size), status='failure')
    with pytest.raises(RemoteConversionError, match='failure'):
        await convert_pdf_remote(pdf, base_url=BASE_URL, transport=transport)


async def test_convert_pdf_remote_rejects_an_http_error(token, pdf):
    transport = httpx.MockTransport(lambda request: httpx.Response(503, text='cold'))
    with pytest.raises(RemoteConversionError, match='503'):
        await convert_pdf_remote(pdf, base_url=BASE_URL, transport=transport)


def test_convert_options_mirror_the_local_pipeline():
    assert CONVERT_OPTIONS['pdf_backend'] == 'pypdfium2'
    assert CONVERT_OPTIONS['table_mode'] == 'accurate'
    assert CONVERT_OPTIONS['to_formats'] == 'json'
    assert CONVERT_OPTIONS['image_export_mode'] == 'embedded'
    assert CONVERT_OPTIONS['include_page_images'] == 'false'
    assert CONVERT_OPTIONS['images_scale'] == str(IMAGE_RESOLUTION_SCALE)


async def test_parse_content_sends_the_pdf_to_the_service_when_configured(
    mocked_root_dir, monkeypatch, pdf, page_size
):
    monkeypatch.setattr(parse.env, 'PDF_PARSING_SERVICE_URL', BASE_URL)
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
    assert remote_convert.await_args.kwargs == {'base_url': BASE_URL}
    assert document_success_path(paper_id).exists()
    assert document_table_image_path(paper_id, 0).exists()
    assert document_image_path(paper_id, 0).exists()
    assert len(json.loads(document_words_json_path(paper_id).read_text())) > 100
