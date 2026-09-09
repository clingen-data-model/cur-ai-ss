"""Single entry point for vision-model calls.

Both VLM tools (pedigree description, table extraction) call this instead of
constructing a client and reading the response themselves, so the stop-reason
handling below exists once rather than twice.

The signature matches the LiteLLM-routed version on the model-routing branch, so
that work replaces this module's internals without touching either call site.
"""

import logging

from openai import OpenAI

from lib.agents.model_factory import vlm_model
from lib.core.environment import env

logger = logging.getLogger(__name__)


def vlm_describe(image_url: str, prompt: str) -> str | None:
    """Ask the vision model about one image; None when there is no usable answer.

    Never raises for a model-side decline: the callers are function tools that
    must return a string sentinel, not an exception. A response truncated at the
    model's output limit is treated as no answer for the same reason a refusal
    is -- a half-extracted table is worse than an admitted failure, because
    nothing distinguishes it from a complete one.

    Provider and network errors do still propagate out of here. Be aware that
    they do not reach the task retry machinery either: both callers are
    function tools, and the agents SDK's default failure_error_function catches
    whatever a tool body raises and hands it to the model as text.
    """
    model = vlm_model()
    client = OpenAI(api_key=env.OPENAI_API_KEY)

    response = client.chat.completions.create(
        model=model,
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
    if finish_reason == 'length':
        logger.warning(
            f'VLM response truncated at the model output limit (model={model}); '
            f'discarding partial output'
        )
        return None
    if finish_reason not in (None, 'stop'):
        logger.warning(
            f'VLM call declined (finish_reason={finish_reason}, model={model})'
        )
        return None

    content = choice.message.content
    return content if isinstance(content, str) else None
