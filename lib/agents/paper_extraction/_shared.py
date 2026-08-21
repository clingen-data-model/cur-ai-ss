"""Plumbing common to every extraction pass."""

import base64
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


def _client() -> OpenAI:
    return OpenAI(api_key=env.OPENAI_API_KEY)


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
    completion = _client().chat.completions.parse(
        model=env.OPENAI_VLM,
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
