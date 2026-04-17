import base64
import logging
from datetime import timedelta
from pathlib import Path

import requests
from google import auth
from google.auth import iam
from google.cloud import storage

from lib.core.environment import env

logger = logging.getLogger(__name__)


class _MetadataServerSigner(iam.Signer):
    """Signer that uses GCE metadata server to sign blobs."""

    def __init__(self, service_account_email: str) -> None:
        self.service_account_email = service_account_email

    def sign_bytes(self, message: bytes) -> bytes:
        """Sign bytes using the GCE metadata server."""
        # Encode the message as base64 for the metadata server
        message_b64 = base64.b64encode(message).decode('utf-8')

        # Call the metadata server signing endpoint
        response = requests.post(
            'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/sign-blob',
            json={'bytesToSign': message_b64},
            headers={'Metadata-Flavor': 'Google'},
            timeout=5,
        )
        response.raise_for_status()

        # Return the signature (already in bytes)
        return base64.b64decode(response.json()['signature'])


# Cache for service account email
_service_account_email_cache: str | None = None


def _get_service_account_email() -> str:
    """Get the default service account email from GCE metadata server."""
    global _service_account_email_cache

    if _service_account_email_cache:
        return _service_account_email_cache

    try:
        # Query GCE metadata server for default service account email
        response = requests.get(
            'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email',
            headers={'Metadata-Flavor': 'Google'},
            timeout=2,
        )
        response.raise_for_status()
        _service_account_email_cache = response.text
        return _service_account_email_cache
    except Exception as e:
        logger.warning(f'Failed to get service account email from metadata: {e}')
        raise RuntimeError(
            'Cannot retrieve service account email from GCE metadata server. '
            'Ensure running on a GCE instance with metadata server enabled.'
        )


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
    """
    # Get service account email from metadata
    service_account_email = _get_service_account_email()

    # Create metadata server signer
    signer = _MetadataServerSigner(service_account_email)

    # Create the signed URL
    client = storage.Client()
    bucket = client.bucket(env.GCS_BUCKET_NAME)
    blob = bucket.blob(object_path)

    signed_url = blob.generate_signed_url(
        version='v4',
        expiration=timedelta(hours=env.GCS_SIGNED_URL_EXPIRY_HOURS),
        method='GET',
        signer=signer,
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
        Signed URL for the uploaded image
    """
    logger.info(f'Uploading image {image_id} for paper {paper_id} to GCS')
    object_path = upload_image_to_gcs(paper_id, image_id, image_path)
    signed_url = get_signed_url(object_path)
    logger.info(f'Generated signed URL: {signed_url[:100]}...')  # Log first 100 chars
    return signed_url
