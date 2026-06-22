"""Shared helper for sending a single image + prompt to the VLM.

Centralizes the OpenAI vision call so every image agent resolves the image URL
the same way (inline data URL in dev, signed GCS URL in prod — see
``lib.misc.gcs.resolve_image_url``) and never routes the (potentially large)
data URL through the LLM prompt or tool-call arguments: the URL is built here,
inside the tool, from a local ``Path``.
"""

from pathlib import Path
from typing import Literal

from lib.core.environment import env
from lib.misc.gcs import resolve_image_url


def describe_image(
    image_path: Path, prompt: str, detail: Literal['auto', 'low', 'high'] = 'high'
) -> str:
    """Send a single local image plus a text prompt to the VLM and return its text.

    The image URL is resolved per environment via ``resolve_image_url`` and built
    here rather than passed in, so a base64 data URL never crosses the model
    boundary.

    Args:
        image_path: Local path to the image file.
        prompt: Instruction text sent alongside the image.
        detail: OpenAI image ``detail`` level ('high' for full-resolution analysis).

    Returns:
        The model's text response, or '' if the response had no content.
    """
    from openai import OpenAI

    client = OpenAI(api_key=env.OPENAI_API_KEY)
    image_url = resolve_image_url(image_path)

    message = client.chat.completions.create(
        model=env.OPENAI_VLM,
        messages=[
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'image_url',
                        'image_url': {'url': image_url, 'detail': detail},
                    },
                    {
                        'type': 'text',
                        'text': prompt,
                    },
                ],
            }
        ],
    )

    content = message.choices[0].message.content
    return content if content is not None else ''
