"""Single entry point for vision-model calls, routed through LiteLLM.

Both VLM tools (pedigree description, table extraction) call this instead of
constructing a provider client themselves, so the model is switchable via
env.VLM_MODEL ('openai/gpt-5.6-sol' or 'anthropic/claude-fable-5-1') without touching
the tools.
"""

import logging

import litellm

from lib.agents.model_factory import provider_api_key
from lib.core.environment import env

logger = logging.getLogger(__name__)


def vlm_describe(image_url: str, prompt: str) -> str | None:
    """Ask the vision model about one image; None when the model declines.

    Never raises for model-side declines: Anthropic models can end a turn
    with a refusal finish reason (safety classifiers), and the callers are
    function tools that must return a string sentinel, not an exception.
    Provider/network errors still raise and are handled by the task retry
    machinery.
    """
    response = litellm.completion(
        model=env.VLM_MODEL,
        api_key=provider_api_key(env.VLM_MODEL),
        messages=[
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'image_url',
                        'image_url': {'url': image_url, 'detail': 'high'},
                    },
                    {'type': 'text', 'text': prompt},
                ],
            }
        ],
    )
    choice = response.choices[0]
    finish_reason = getattr(choice, 'finish_reason', None)
    if finish_reason not in (None, 'stop', 'length', 'end_turn'):
        logger.warning(
            f'VLM call declined (finish_reason={finish_reason}, model={env.VLM_MODEL})'
        )
        return None
    content = choice.message.content
    return content if isinstance(content, str) else None
