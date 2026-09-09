import base64

import pytest

from lib.misc.images import image_to_data_url


def test_image_to_data_url_encodes_bytes_with_guessed_mime(tmp_path):
    image_path = tmp_path / 'pedigree.png'
    image_path.write_bytes(b'fake-png-bytes')

    data_url = image_to_data_url(image_path)

    expected = base64.b64encode(b'fake-png-bytes').decode('ascii')
    assert data_url == f'data:image/png;base64,{expected}'


def test_image_to_data_url_falls_back_to_png_for_unknown_extension(tmp_path):
    image_path = tmp_path / 'table.unknownext'
    image_path.write_bytes(b'bytes')

    assert image_to_data_url(image_path).startswith('data:image/png;base64,')


def test_image_to_data_url_raises_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        image_to_data_url(tmp_path / 'absent.png')
