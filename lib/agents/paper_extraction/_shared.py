"""Plumbing common to every extraction pass."""

import base64
import functools
import logging
from typing import Any, TypeVar

from openai import OpenAI
from pydantic import BaseModel

from lib.agents.core_extraction_rules import CORE_EXTRACTION_SPEC
from lib.core.environment import env
from lib.core.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)

READING_THE_PAPER = """Everything comes from the attached PDF. You have no lookup tools,
so never supply a value the paper does not print.

Clinical values, especially ages, frequently appear only in tables. A table may be printed
sideways, or continued across pages under a "Continued" heading -- continuation pages are
part of the same table and describe the same series of patients. A value you could not read
is not the same as a value the paper does not report."""


# Left to itself the SDK will wait on a socket indefinitely: a paper 89 run sat
# blocked on the details pass for two hours and 47 minutes at 0% CPU with the
# connection still ESTABLISHED. The bound has to hold against the worker's
# 3600s lease for this task, and passes 2-4 run concurrently, so the worst case
# is pedigree + structure + one of the concurrent three -- three legs at
# 2 * 480s each, which fits with room to spare. The observed slowest pass was
# 163s, so this is roughly 3x headroom before a retry, not a tight collar.
_ATTEMPT_TIMEOUT_S = 480.0
_MAX_RETRIES = 1


@functools.cache
def _client() -> OpenAI:
    """One client for the process: each pass otherwise built its own connection
    pool, which is how a single hung run held five sockets open."""
    return OpenAI(
        api_key=env.OPENAI_API_KEY,
        timeout=_ATTEMPT_TIMEOUT_S,
        max_retries=_MAX_RETRIES,
    )


def _pdf_part(paper_id: int, pdf_bytes: bytes) -> dict[str, Any]:
    return {
        'type': 'file',
        'file': {
            'filename': f'paper_{paper_id}.pdf',
            'file_data': 'data:application/pdf;base64,'
            + base64.b64encode(pdf_bytes).decode(),
        },
    }


def _run(
    label: str,
    paper_id: int,
    schema: type[T],
    instructions: str,
    content: list[dict[str, Any]],
) -> T | None:
    logger.info(f'Paper {paper_id} {label}: requesting')
    completion = _client().chat.completions.parse(
        model=env.OPENAI_API_DEPLOYMENT,
        messages=[
            {'role': 'system', 'content': instructions + CORE_EXTRACTION_SPEC},
            {'role': 'user', 'content': content},  # type: ignore[misc,list-item]
        ],
        response_format=schema,
    )
    usage = completion.usage
    if usage:
        logger.info(
            f'Paper {paper_id} {label}: {usage.prompt_tokens} prompt, '
            f'{usage.completion_tokens} completion tokens'
        )
    return completion.choices[0].message.parsed
