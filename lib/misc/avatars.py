"""Avatar image storage on the VM disk.

Avatars live under ``{CAA_ROOT}/avatars/`` beside ``extracted_pdfs/``, and are
served by the same ``StaticFiles`` mount that already serves PDF thumbnails. That
mount is unauthenticated, which is a requirement rather than an oversight here:
an ``<img src>`` cannot carry an Authorization header, so anything a browser
renders directly has to be reachable without one.

Object storage was deliberately removed in #138/#139 (the bucket, its IAM, and
the google-cloud-storage dependency all went), so disk is the only option that
does not reintroduce it.

Everything is normalised to PNG through Pillow rather than stored as uploaded.
That is what makes the upload safe: the bytes that reach disk are ones Pillow
re-encoded from a successfully decoded image, so a file that merely claims to be
a PNG -- or is a real image with a payload appended -- cannot survive the round
trip. Content type from the client is not trusted and never consulted.
"""

import io
import logging
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from lib.core.environment import env

logger = logging.getLogger(__name__)

# Generous for a face, small enough that a full read is never a memory concern.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# Avatars render at 32-64px; 512 is a retina-safe ceiling that keeps files tiny.
MAX_DIMENSION = 512


class InvalidAvatarError(ValueError):
    """The upload was not a decodable image, or was too large."""


def avatars_dir() -> Path:
    return Path(env.CAA_ROOT) / 'avatars'


def avatar_path(user_id: int) -> Path:
    """Where this user's avatar lives. One file per user, always .png."""
    return avatars_dir() / f'{user_id}.png'


def store_avatar(user_id: int, data: bytes) -> Path:
    """Decode, normalise and write ``data`` as this user's avatar.

    Raises InvalidAvatarError for anything Pillow cannot open as an image, so the
    caller can turn it into a 400 rather than a 500.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise InvalidAvatarError(
            f'Image is {len(data)} bytes; the limit is {MAX_UPLOAD_BYTES}.'
        )
    if not data:
        raise InvalidAvatarError('Image is empty.')

    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()  # force a real decode; Image.open is lazy
            # RGBA keeps transparency; anything exotic (palette, CMYK, 16-bit)
            # collapses to something a browser will certainly render.
            converted = image.convert('RGBA')
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidAvatarError('Not a readable image.') from exc

    converted.thumbnail((MAX_DIMENSION, MAX_DIMENSION))

    destination = avatar_path(user_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Write beside the target and replace, so a reader never sees a half-written
    # file and a failed encode cannot destroy the existing avatar.
    staging = destination.with_suffix('.png.tmp')
    try:
        converted.save(staging, format='PNG', optimize=True)
        staging.replace(destination)
    finally:
        staging.unlink(missing_ok=True)

    logger.info(
        f'Stored avatar for user {user_id} ({destination.stat().st_size} bytes)'
    )
    return destination


def delete_avatar(user_id: int) -> bool:
    """Remove this user's avatar. True if one was there."""
    path = avatar_path(user_id)
    if not path.exists():
        return False
    path.unlink()
    return True
