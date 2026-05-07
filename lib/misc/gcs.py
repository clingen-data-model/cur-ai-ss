import logging
from datetime import timedelta
from pathlib import Path

from google.auth import default
from google.auth.transport.requests import Request
from google.cloud import storage

from lib.core.environment import env
from lib.misc.pdf.paths import pdf_image_path

logger = logging.getLogger(__name__)


def upload_image_to_gcs(paper_id: int, image_id: int, image_path: Path) -> str:
    """Upload an image to GCS and return the object path.

    Args:
        paper_id: Paper ID
        image_id: Image ID
        image_path: Local path to the image file

    Returns:
        GCS object path (e.g., 'images/123/0.png')
    """
    if not image_path.exists():
        raise FileNotFoundError(f'Image file not found: {image_path}')

    # Use ADC (Application Default Credentials) for upload
    client = storage.Client()
    bucket = client.bucket(env.GCS_BUCKET_NAME)

    # Deterministic GCS path
    object_path = f'images/{paper_id}/{image_id}.png'

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


def upload_and_sign_image(paper_id: int, image_id: int, image_path: Path) -> str:
    """Upload an image to GCS and return a signed URL.

    Args:
        paper_id: Paper ID
        image_id: Image ID
        image_path: Local path to the image file

    Returns:
        Signed URL for the uploaded image, or a local API URL if GCS upload is disabled
    """
    if env.DISABLE_GCS_UPLOAD:
        stored_path = pdf_image_path(paper_id, image_id)
        local_url = f'{env.PROTOCOL}{env.API_ENDPOINT}{stored_path}'
        logger.info(f'GCS upload disabled, using local API URL: {local_url}')
        return local_url

    logger.info(f'Uploading image {image_id} for paper {paper_id} to GCS')
    object_path = upload_image_to_gcs(paper_id, image_id, image_path)
    signed_url = get_signed_url(object_path)
    logger.info(f'Generated signed URL: {signed_url[:100]}...')  # Log first 100 chars
    return signed_url
