"""Avatar upload/delete on /auth/me/avatar."""

import io

from PIL import Image

from lib.misc.avatars import avatar_path


def _png(size=(64, 64)) -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', size, 'blue').save(buffer, format='PNG')
    return buffer.getvalue()


def _upload(client, data: bytes, filename='me.png', content_type='image/png'):
    return client.put(
        '/auth/me/avatar', files={'image': (filename, data, content_type)}
    )


def test_upload_stores_the_file_and_stamps_the_user(client, test_user):
    response = _upload(client, _png())

    assert response.status_code == 200
    assert avatar_path(test_user.id).exists()
    assert response.json()['avatar_updated_at'] is not None


def test_avatar_url_is_null_until_one_is_uploaded(client):
    assert client.get('/auth/me').json()['avatar_url'] is None


def test_avatar_url_carries_a_cache_buster(client):
    """The path never changes and the static mount sends a 24h Cache-Control, so
    without ?v= a new upload would stay invisible in the browser."""
    url = _upload(client, _png()).json()['avatar_url']

    assert url is not None
    assert '?v=' in url


def test_a_lying_content_type_is_rejected(client, test_user):
    """content_type is not consulted -- validity comes from decoding the bytes."""
    response = _upload(client, b'this is not a png', content_type='image/png')

    assert response.status_code == 400
    assert not avatar_path(test_user.id).exists()
    assert client.get('/auth/me').json()['avatar_url'] is None


def test_a_real_image_with_a_wrong_content_type_is_accepted(client):
    """The converse: bytes decide, so a mislabelled but genuine image is fine."""
    assert (
        _upload(client, _png(), content_type='application/octet-stream').status_code
        == 200
    )


def test_delete_removes_file_and_clears_the_column(client, test_user):
    _upload(client, _png())

    response = client.delete('/auth/me/avatar')

    assert response.status_code == 200
    assert response.json()['avatar_url'] is None
    assert not avatar_path(test_user.id).exists()


def test_delete_is_idempotent(client):
    assert client.delete('/auth/me/avatar').status_code == 200


def test_upload_requires_authentication(unauth_client):
    assert _upload(unauth_client, _png()).status_code == 401
