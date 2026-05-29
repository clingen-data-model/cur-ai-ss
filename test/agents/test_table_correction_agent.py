from pathlib import Path
from unittest.mock import Mock

from lib.agents import table_correction_agent


def test_image_url_for_openai_uses_gcs_when_uploads_enabled(monkeypatch, tmp_path):
    image_path = tmp_path / 'table.png'
    image_path.write_bytes(b'image bytes')
    upload_and_sign_image = Mock(return_value='https://example.com/signed-table.png')

    monkeypatch.setattr(table_correction_agent.env, 'DISABLE_GCS_UPLOAD', False)
    monkeypatch.setattr(
        'lib.misc.gcs.upload_and_sign_image',
        upload_and_sign_image,
    )

    image_url = table_correction_agent._image_url_for_openai(image_path)

    assert image_url == 'https://example.com/signed-table.png'
    upload_and_sign_image.assert_called_once_with(image_path)


def test_image_url_for_openai_uses_data_url_when_uploads_disabled(
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

    monkeypatch.setattr(table_correction_agent.env, 'DISABLE_GCS_UPLOAD', True)

    image_url = table_correction_agent._image_url_for_openai(image_path)

    assert image_url == (
        'data:image/png;base64,'
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVQ'
        'I12P4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC'
    )
