"""Single entry point for vision-model calls.

Both VLM tools (pedigree description, table extraction) call this instead of
constructing a client and reading the response themselves, so the stop-reason
handling below exists once rather than twice.

Calls go through litellm rather than the OpenAI client so VLM_MODEL is a
one-line env change: the vision path has no conversation_id, no structured
output and no tools, so it touches none of what still pins the extraction
agents to the Responses API.
"""

import logging

import litellm

from lib.agents.model_factory import provider_api_key, vlm_model

logger = logging.getLogger(__name__)

# Bound the reply explicitly. Left unset, litellm fills in the model's ceiling
# (128k on Anthropic), and a non-streaming call with that much headroom invites
# an HTTP timeout rather than an answer.
MAX_TOKENS = 16384


def vlm_describe(image_url: str, prompt: str) -> str | None:
    """Ask the vision model about one image; None when there is no usable answer.

    Never raises for a model-side decline: the callers are function tools that
    must return a string sentinel, not an exception. A response truncated at the
    model's output limit is treated as no answer for the same reason a refusal
    is -- a half-extracted table is worse than an admitted failure, because
    nothing distinguishes it from a complete one.

    Provider and network errors propagate, and are meant to: not reaching the
    model at all is a task failure, not a finding about the paper. Both callers
    pass failure_error_function=None so the exception is not converted into tool
    output, which puts it in front of the worker -- FAILED with the message
    stored, successors not enqueued, and retried up to MAX_RETRIES.

    So the split is: None for anything the model said, an exception for anything
    that stopped us asking it.
    """
    model = vlm_model()

    response = litellm.completion(
        model=model,
        api_key=provider_api_key(model),
        max_tokens=MAX_TOKENS,
        messages=[
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'image_url',
                        # detail is ignored on Anthropic, still meaningful on OpenAI.
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
    # litellm normalizes Anthropic's 'end_turn' to 'stop', so the accepted set
    # stays the same across providers.
    if finish_reason not in (None, 'stop'):
        logger.warning(
            f'VLM call declined (finish_reason={finish_reason}, model={model})'
        )
        return None

    content = choice.message.content
    return content if isinstance(content, str) else None
