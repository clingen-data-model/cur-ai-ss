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

# LiteLLM otherwise defaults this to the model's ceiling (128k on current
# Anthropic models), and a ceiling that high on a non-streaming call invites
# HTTP timeouts. Large enough for a full markdown table.
VLM_MAX_TOKENS = 16384


def vlm_describe(image_url: str, prompt: str) -> str | None:
    """Ask the vision model about one image; None when there is no usable answer.

    Never raises for model-side declines: Anthropic models can end a turn
    with a refusal finish reason (safety classifiers), and the callers are
    function tools that must return a string sentinel, not an exception.
    A response truncated at max_tokens is also treated as no answer — a
    half-extracted table is worse than an admitted failure, because callers
    cannot tell it apart from a complete one. Provider/network errors still
    raise and are handled by the task retry machinery.
    """
    response = litellm.completion(
        model=env.VLM_MODEL,
        api_key=provider_api_key(env.VLM_MODEL),
        max_tokens=VLM_MAX_TOKENS,
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
    # LiteLLM normalizes provider stop reasons to the OpenAI set, so Anthropic's
    # 'end_turn' arrives as 'stop', 'max_tokens' as 'length', 'refusal' as
    # 'content_filter'.
    finish_reason = getattr(choice, 'finish_reason', None)
    if finish_reason == 'length':
        logger.warning(
            f'VLM response truncated at max_tokens={VLM_MAX_TOKENS} '
            f'(model={env.VLM_MODEL}); discarding partial output'
        )
        return None
    if finish_reason not in (None, 'stop'):
        logger.warning(
            f'VLM call declined (finish_reason={finish_reason}, model={env.VLM_MODEL})'
        )
        return None
    content = choice.message.content
    return content if isinstance(content, str) else None
