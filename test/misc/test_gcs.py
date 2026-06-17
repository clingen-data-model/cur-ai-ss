from pathlib import Path
from unittest.mock import Mock

from lib.misc import gcs


def test_upload_and_sign_image_uses_gcs_when_uploads_enabled(monkeypatch, tmp_path):
    image_path = tmp_path / 'table.png'
    image_path.write_bytes(b'image bytes')
    upload_image_to_gcs = Mock(return_value='tables/table.png')
    get_signed_url = Mock(return_value='https://example.com/signed-table.png')

    monkeypatch.setattr(gcs.env, 'DISABLE_GCS_UPLOAD', False)
    monkeypatch.setattr(gcs, 'upload_image_to_gcs', upload_image_to_gcs)
    monkeypatch.setattr(gcs, 'get_signed_url', get_signed_url)

    image_url = gcs.upload_and_sign_image(image_path)

    assert image_url == 'https://example.com/signed-table.png'
    upload_image_to_gcs.assert_called_once_with(image_path)


def test_upload_and_sign_image_uses_data_url_when_uploads_disabled(
    monkeypatch, tmp_path
):
    png_bytes = (
        b'\x89PNG\r\n\x1a\n'
        b'\x00\x00\x00\rIHDR'
        b'\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00'
        b'\x90wS\xde'
        b'\x00\x00\x00\x0cIDAT'
        b'\x08\xd7c\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00'
        b'\xc9\xfe\x92\xef'
        b'\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    image_path = Path(tmp_path) / 'one_pixel.png'
    image_path.write_bytes(png_bytes)

    monkeypatch.setattr(gcs.env, 'DISABLE_GCS_UPLOAD', True)

    image_url = gcs.upload_and_sign_image(image_path)

    assert image_url == (
        'data:image/png;base64,'
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVQ'
        'I12P4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC'
    )
