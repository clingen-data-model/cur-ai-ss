import tarfile
from pathlib import Path

import pytest
from docling_core.types.doc import (
    BoundingBox,
    CoordOrigin,
    DoclingDocument,
    ImageRef,
    ProvenanceItem,
    Size,
)
from fastapi.testclient import TestClient
from PIL import Image

from lib.docling_service import app as service
from lib.misc.pdf.convert_archive import pack_tree, unpack_tree
from lib.misc.pdf.convert_result import ConvertResult, load_convert_result
from lib.misc.pdf.words import WordLoc


def _result() -> ConvertResult:
    doc = DoclingDocument(name='test')
    doc.add_page(page_no=1, size=Size(width=600, height=800))
    doc.add_picture(
        image=ImageRef.from_pil(Image.new('RGB', (40, 30), (0, 90, 200)), dpi=288),
        prov=ProvenanceItem(
            page_no=1,
            bbox=BoundingBox(
                l=10, t=400, r=300, b=340, coord_origin=CoordOrigin.BOTTOMLEFT
            ),
            charspan=(0, 0),
        ),
    )
    word = WordLoc(
        page_idx=0, word='gene', x0=1, y0=2, x1=3, y1=2, x2=3, y2=4, x3=1, y3=4
    )
    return ConvertResult(document=doc, words=[word])


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / 'caa'
    root.mkdir()
    monkeypatch.setattr(service, 'ALLOWED_ROOT', root)
    monkeypatch.setattr(service, 'convert_content', lambda content, fmt: _result())
    return TestClient(service.app), root, tmp_path


def _body(root: Path, tmp_path: Path, **overrides: str) -> dict[str, str]:
    (tmp_path / 'in.pdf').write_bytes(b'%PDF-1.4 fake')
    body = {
        'input_uri': f'file://{tmp_path}/in.pdf',
        'output_uri': f'file://{tmp_path}/out/result.tar.gz',
        'json_path': str(root / 'extracted_pdfs/7/raw.json'),
        'words_path': str(root / 'extracted_pdfs/7/words.json'),
    }
    return {**body, **overrides}


def test_convert_returns_a_loadable_archive_and_cleans_up(client):
    http, root, tmp_path = client
    resp = http.post('/convert', json=_body(root, tmp_path))
    assert resp.status_code == 200, resp.text

    out_dir = root / 'extracted_pdfs/7'
    assert not out_dir.exists()  # nothing left behind on the service

    unpack_tree(tmp_path / 'out/result.tar.gz', out_dir)
    loaded = load_convert_result(out_dir / 'raw.json', out_dir / 'words.json')
    (picture,) = loaded.document.pictures
    assert picture.get_image(loaded.document) is not None
    assert loaded.words == _result().words


@pytest.mark.parametrize(
    'overrides',
    [
        {'json_path': '/etc/raw.json', 'words_path': '/etc/words.json'},
        {'json_path': 'relative/raw.json', 'words_path': 'relative/words.json'},
        {'json_path': 'ROOT/../../etc/raw.json', 'words_path': 'ROOT/words.json'},
        {'json_path': 'ROOT/raw.json', 'words_path': 'ROOT/words.json'},
        {'words_path': 'ROOT/extracted_pdfs/8/words.json'},
    ],
)
def test_convert_rejects_paths_outside_a_subdirectory_of_the_root(client, overrides):
    http, root, tmp_path = client
    fixed = {k: v.replace('ROOT', str(root)) for k, v in overrides.items()}
    resp = http.post('/convert', json=_body(root, tmp_path, **fixed))
    assert resp.status_code == 400


def test_convert_rejects_xlsx(client):
    http, root, tmp_path = client
    resp = http.post('/convert', json=_body(root, tmp_path, file_format='xlsx'))
    assert resp.status_code == 400


def test_unpack_refuses_members_outside_the_expected_directory(tmp_path):
    src = tmp_path / 'src'
    src.mkdir()
    (src / 'a.txt').write_text('a')
    archive = tmp_path / 'a.tar.gz'
    pack_tree(src, archive)

    with pytest.raises(ValueError, match='outside'):
        unpack_tree(archive, tmp_path / 'somewhere_else')


def test_unpack_refuses_links(tmp_path):
    archive = tmp_path / 'evil.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        link = tarfile.TarInfo(str(tmp_path / 'dest/link').lstrip('/'))
        link.type = tarfile.SYMTYPE
        link.linkname = '/etc/passwd'
        tar.addfile(link)

    with pytest.raises(ValueError, match='unsupported'):
        unpack_tree(archive, tmp_path / 'dest')
