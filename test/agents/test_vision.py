from pathlib import Path
from unittest.mock import MagicMock, patch

from lib.agents import vision


def _mock_openai_returning(content):
    """Build a mock OpenAI client whose chat completion returns ``content``."""
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    completion = MagicMock()
    completion.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.return_value = completion
    return client


def test_describe_image_resolves_url_and_returns_content():
    image_path = Path('/tmp/example.png')
    client = _mock_openai_returning('extracted text')

    with (
        patch.object(
            vision, 'resolve_image_url', return_value='data:image/png;base64,AAA'
        ),
        patch('openai.OpenAI', return_value=client),
    ):
        result = vision.describe_image(image_path, 'do the thing')

    assert result == 'extracted text'

    # The resolved URL is built inside describe_image and sent to the VLM.
    _, kwargs = client.chat.completions.create.call_args
    content = kwargs['messages'][0]['content']
    image_part = next(p for p in content if p['type'] == 'image_url')
    text_part = next(p for p in content if p['type'] == 'text')
    assert image_part['image_url']['url'] == 'data:image/png;base64,AAA'
    assert image_part['image_url']['detail'] == 'high'
    assert text_part['text'] == 'do the thing'


def test_describe_image_returns_empty_string_when_no_content():
    client = _mock_openai_returning(None)

    with (
        patch.object(
            vision, 'resolve_image_url', return_value='https://example.com/x.png'
        ),
        patch('openai.OpenAI', return_value=client),
    ):
        result = vision.describe_image(Path('/tmp/x.png'), 'prompt')

    assert result == ''
