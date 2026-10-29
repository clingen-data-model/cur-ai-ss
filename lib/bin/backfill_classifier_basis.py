#!/usr/bin/env python3
"""Fill papers.is_paper_relevant_evidence for papers classified before the
column existed (migration d4e8f1a2b3c5).

The handler stored only the verdict; the block the classifier actually
returned, verdict and basis, is still the last assistant message of the
task's agent conversation (lib.tasks.agent_session, keyed by the task id).
This reads it from there for every paper that has a verdict and no block,
and stores it the way the handler now does, with the model-facing "basis"
key mapped back to "reasoning". A paper whose conversation is gone (a retry
cleared it, or the session file was lost) is left None and counted; the
next classifier run fills it.

Fills only rows whose block is None, so it is safe to re-run.

Usage:
    uv run python -m lib.bin.backfill_classifier_basis
"""

import asyncio
import json
import logging

from lib.agents.model_facing import from_model_keys
from lib.api.db import session_scope
from lib.core.logging import setup_logging
from lib.models.evidence_block import ReasoningBlock
from lib.models.paper import PaperDB
from lib.tasks.agent_session import agent_session
from lib.tasks.models import TaskDB, TaskStatus, TaskType

setup_logging()
logger = logging.getLogger(__name__)


async def classifier_block(task_id: int) -> dict | None:
    """The verdict block from the task's conversation, or None when the
    conversation holds no parseable final answer."""
    items = await agent_session(task_id).get_items()
    for item in reversed(items):
        if item.get('role') != 'assistant':
            continue
        content = item.get('content')
        if not isinstance(content, list):
            continue
        for part in content:
            text = part.get('text') if isinstance(part, dict) else None
            if not text:
                continue
            try:
                answer = from_model_keys(json.loads(text))
                block = ReasoningBlock[bool].model_validate(answer['is_paper_relevant'])
            except (ValueError, KeyError, TypeError):
                return None
            return block.model_dump()
    return None


async def backfill() -> None:
    with session_scope() as session:
        pending = [
            (paper.id, task.id)
            for paper, task in session.query(PaperDB, TaskDB)
            .join(TaskDB, TaskDB.paper_id == PaperDB.id)
            .filter(
                PaperDB.is_paper_relevant.isnot(None),
                PaperDB.is_paper_relevant_evidence.is_(None),
                TaskDB.type == TaskType.PAPER_CLASSIFIER,
                TaskDB.status == TaskStatus.COMPLETED,
            )
            .order_by(PaperDB.id)
        ]

    filled = 0
    for paper_id, task_id in pending:
        block = await classifier_block(task_id)
        if block is None:
            logger.info(f'Paper {paper_id}: no answer in task {task_id} conversation')
            continue
        with session_scope() as session:
            paper = session.get(PaperDB, paper_id)
            if paper is None or paper.is_paper_relevant_evidence is not None:
                continue
            if block['value'] != paper.is_paper_relevant:
                logger.warning(
                    f'Paper {paper_id}: conversation verdict {block["value"]} differs '
                    f'from the stored {paper.is_paper_relevant}; skipped'
                )
                continue
            paper.is_paper_relevant_evidence = block
        filled += 1
        logger.info(f'Paper {paper_id}: {block["reasoning"][:80]!r}')

    logger.info(f'Done: {filled} of {len(pending)} papers filled')


if __name__ == '__main__':
    asyncio.run(backfill())
