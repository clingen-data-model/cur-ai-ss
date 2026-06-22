import base64
import logging
import mimetypes
from datetime import timedelta
from pathlib import Path

from google.auth import default
from google.auth.transport.requests import Request
from google.cloud import storage

from lib.core.environment import env
from lib.misc.pdf.paths import pdf_image_path

logger = logging.getLogger(__name__)


def upload_image_to_gcs(image_path: Path) -> str:
    """Upload an image to GCS and return the object path.

    Args:
        image_path: Local path to the image file

    Returns:
        GCS object path
    """
    if not image_path.exists():
        raise FileNotFoundError(f'Image file not found: {image_path}')

    # Use relative path from CAA_ROOT as GCS object path
    relative_path = image_path.relative_to(Path(env.CAA_ROOT))
    object_path = str(relative_path)

    # Use ADC (Application Default Credentials) for upload
    client = storage.Client()
    bucket = client.bucket(env.GCS_BUCKET_NAME)

    blob = bucket.blob(object_path)
    blob.upload_from_filename(str(image_path))

    logger.info(f'Uploaded image to gs://{env.GCS_BUCKET_NAME}/{object_path}')
    return object_path


def get_signed_url(object_path: str) -> str:
    """Generate a signed URL (GET-only) for a GCS object.

    Args:
        object_path: GCS object path (e.g., 'images/123/0.png')

    Returns:
        Signed URL valid for GCS_SIGNED_URL_EXPIRY_HOURS hours

    Requires: GOOGLE_APPLICATION_CREDENTIALS pointing to a service account JSON key
    """
    client = storage.Client()
    bucket = client.bucket(env.GCS_BUCKET_NAME)
    blob = bucket.blob(object_path)
    credentials, project = default()
    credentials.refresh(Request())
    signed_url = blob.generate_signed_url(
        version='v4',
        expiration=timedelta(hours=env.GCS_SIGNED_URL_EXPIRY_HOURS),
        method='GET',
        service_account_email=credentials.service_account_email,  # type: ignore[attr-defined]
        access_token=credentials.token,
    )
    logger.info(f'Generated signed URL for {object_path}')
    return signed_url


def _image_path_to_data_url(image_path: Path) -> str:
    """Encode a local image path as a base64 data URL for VLM image input.

    See: https://developers.openai.com/api/docs/guides/images-vision?format=base64-encoded
    """
    mime_type = mimetypes.guess_type(image_path.name)[0] or 'image/png'
    image_b64 = base64.b64encode(image_path.read_bytes()).decode('ascii')
    return f'data:{mime_type};base64,{image_b64}'


def resolve_image_url(image_path: Path) -> str:
    """Return a VLM-readable URL for a local image, per environment.

    In local dev (``DISABLE_GCS_UPLOAD``) returns an inline base64 data URL that
    OpenAI's servers can read directly — a ``localhost`` static-file URL is
    unreachable from OpenAI and yields a 400 ``invalid_image_url``. In prod the
    image is uploaded to GCS and a signed URL is returned (smaller payloads).

    Image token cost is identical either way; base64 only inflates request bytes.

    Args:
        image_path: Local path to the image file (from pdf_image_path or pdf_table_image_path)

    Returns:
        A base64 data URL (dev) or a GCS signed URL (prod).
    """
    if not image_path.exists():
        raise FileNotFoundError(f'Image file not found: {image_path}')

    if env.DISABLE_GCS_UPLOAD:
        logger.info(f'GCS upload disabled, encoding {image_path} as a data URL')
        return _image_path_to_data_url(image_path)

    logger.info(f'Uploading image {image_path.name} to GCS')
    object_path = upload_image_to_gcs(image_path)
    signed_url = get_signed_url(object_path)
    logger.info(f'Generated signed URL: {signed_url[:100]}...')  # Log first 100 chars
    return signed_url
