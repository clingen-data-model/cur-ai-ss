import base64
import logging
import mimetypes
from pathlib import Path

logger = logging.getLogger(__name__)


def image_to_data_url(image_path: Path) -> str:
    """Encode a local image as a base64 data URL for direct model consumption.

    Both Anthropic and OpenAI accept a data URL in place of a fetchable URL, so
    images never have to leave the process.
    """
    if not image_path.exists():
        raise FileNotFoundError(f'Image file not found: {image_path}')

    mime_type = mimetypes.guess_type(image_path.name)[0] or 'image/png'
    image_b64 = base64.b64encode(image_path.read_bytes()).decode('ascii')
    logger.info(f'Encoded {image_path.name} as a {mime_type} data URL')
    return f'data:{mime_type};base64,{image_b64}'
