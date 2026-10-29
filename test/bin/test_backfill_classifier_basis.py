"""The backfill reads the classifier's block out of the task conversation."""

import json

import pytest

from lib.bin import backfill_classifier_basis as backfill


class _Items:
    def __init__(self, items: list[dict]) -> None:
        self.items = items

    async def get_items(self, limit: int | None = None) -> list[dict]:
        return self.items


def _assistant(text: str) -> dict:
    return {'role': 'assistant', 'content': [{'type': 'output_text', 'text': text}]}


@pytest.mark.asyncio
async def test_the_block_is_the_last_answer_with_basis_mapped_back(monkeypatch):
    """What dev-caa's task 36 holds for paper 47: the model-facing "basis"
    key, which is "reasoning" in storage."""
    items = [
        {'role': 'user', 'content': 'PAPER AND GENE CONTEXT ...'},
        _assistant(
            json.dumps(
                {
                    'is_paper_relevant': {
                        'value': False,
                        'basis': 'This is mainly a mouse study of Grxcr2.',
                    }
                }
            )
        ),
    ]
    monkeypatch.setattr(backfill, 'agent_session', lambda task_id: _Items(items))

    assert await backfill.classifier_block(36) == {
        'value': False,
        'reasoning': 'This is mainly a mouse study of Grxcr2.',
    }


@pytest.mark.asyncio
async def test_a_cleared_or_unparseable_conversation_yields_none(monkeypatch):
    for items in ([], [_assistant('not json')], [_assistant('{"other": 1}')]):
        monkeypatch.setattr(
            backfill, 'agent_session', lambda task_id, items=items: _Items(items)
        )
        assert await backfill.classifier_block(1) is None
