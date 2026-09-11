"""Avatar storage: what reaches disk is always a re-encoded PNG."""

import io

import pytest
from PIL import Image

from lib.misc.avatars import (
    MAX_DIMENSION,
    MAX_UPLOAD_BYTES,
    InvalidAvatarError,
    avatar_path,
    delete_avatar,
    store_avatar,
)


def _image_bytes(fmt='PNG', size=(64, 64), mode='RGB') -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, size, 'red').save(buffer, format=fmt)
    return buffer.getvalue()


def test_stores_a_png(mocked_root_dir):
    path = store_avatar(1, _image_bytes())

    assert path == avatar_path(1)
    assert path.exists()
    with Image.open(path) as written:
        assert written.format == 'PNG'


def test_normalises_jpeg_to_png(mocked_root_dir):
    """The stored file is always PNG regardless of what arrived."""
    store_avatar(1, _image_bytes(fmt='JPEG'))

    with Image.open(avatar_path(1)) as written:
        assert written.format == 'PNG'


def test_downscales_large_images(mocked_root_dir):
    store_avatar(1, _image_bytes(size=(2000, 1000)))

    with Image.open(avatar_path(1)) as written:
        assert max(written.size) == MAX_DIMENSION
        # thumbnail() preserves aspect ratio rather than squashing to a square.
        assert written.size == (MAX_DIMENSION, MAX_DIMENSION // 2)


def test_leaves_small_images_alone(mocked_root_dir):
    store_avatar(1, _image_bytes(size=(48, 48)))

    with Image.open(avatar_path(1)) as written:
        assert written.size == (48, 48)


def test_rejects_a_file_that_only_claims_to_be_an_image(mocked_root_dir):
    """The whole point of decoding rather than trusting content_type: a PNG
    magic number in front of arbitrary bytes must not reach disk."""
    with pytest.raises(InvalidAvatarError, match='readable image'):
        store_avatar(1, b'\x89PNG\r\n\x1a\n' + b'not actually an image')

    assert not avatar_path(1).exists()


def test_rejects_empty_and_oversized(mocked_root_dir):
    with pytest.raises(InvalidAvatarError, match='empty'):
        store_avatar(1, b'')
    with pytest.raises(InvalidAvatarError, match='limit'):
        store_avatar(1, b'x' * (MAX_UPLOAD_BYTES + 1))


def test_a_failed_upload_leaves_the_previous_avatar_intact(mocked_root_dir):
    """Staging + replace: a bad second upload must not destroy a good first one."""
    store_avatar(1, _image_bytes(size=(48, 48)))

    with pytest.raises(InvalidAvatarError):
        store_avatar(1, b'garbage')

    with Image.open(avatar_path(1)) as written:
        assert written.size == (48, 48)
    assert not avatar_path(1).with_suffix('.png.tmp').exists()


def test_replacing_overwrites_in_place(mocked_root_dir):
    store_avatar(1, _image_bytes(size=(48, 48)))
    store_avatar(1, _image_bytes(size=(96, 96)))

    with Image.open(avatar_path(1)) as written:
        assert written.size == (96, 96)


def test_users_do_not_collide(mocked_root_dir):
    store_avatar(1, _image_bytes(size=(48, 48)))
    store_avatar(2, _image_bytes(size=(96, 96)))

    with Image.open(avatar_path(1)) as one:
        assert one.size == (48, 48)
    with Image.open(avatar_path(2)) as two:
        assert two.size == (96, 96)


def test_delete(mocked_root_dir):
    store_avatar(1, _image_bytes())

    assert delete_avatar(1) is True
    assert not avatar_path(1).exists()
    assert delete_avatar(1) is False
