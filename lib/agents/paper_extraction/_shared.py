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
is not the same as a value the paper does not report.

The PDF carries an embedded text layer as well as the printed pages, and that text layer is
often wrong: papers are typeset with fonts whose character mapping is broken, so a
character reads as something else entirely. Seen in these papers: ">" extracted as "4" or
as a space, so c.98T>G reads "c.98T 4 G"; "<=" extracted as "5", so an onset of "<=1 y"
reads "51 y"; a minus sign extracted as the letter I. Read every value off the printed page
as it appears to the eye. Where the two disagree, the page is right and the text layer is
wrong. Never copy a value carrying an artifact like these -- a nonsensical HGVS operator, a
biologically impossible age -- and never let one merge two values into one field."""


# Passing the PDF is cheap: an 850KB paper is ~16.5k tokens, only 1.5x the
# reconstructed text. It also caches at 99.5% -- but only against an identical
# request, because response_format is part of the cache key and every pass has
# its own schema. Measured: same schema and different trailing text cached
# 16,384 of 16,507 tokens; same prefix with a different schema cached 0. So a
# pass caches against its own retries and reruns, never against another pass,
# and no amount of reordering the message changes that.


# Left to itself the SDK will wait on a socket indefinitely: a paper 89 run sat
# blocked on the details pass for two hours and 47 minutes at 0% CPU with the
# connection still ESTABLISHED. The observed slowest pass was 163s, so this is
# roughly 3x headroom before a retry, not a tight collar, and two attempts stay
# well inside the worker's lease.
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
        details = usage.prompt_tokens_details
        cached = getattr(details, 'cached_tokens', 0) or 0
        share = cached / usage.prompt_tokens if usage.prompt_tokens else 0.0
        logger.info(
            f'[TOKENS] {label.upper()}: input={usage.prompt_tokens} '
            f'cached={cached} ({share:.1%}) output={usage.completion_tokens}'
        )
    return completion.choices[0].message.parsed
