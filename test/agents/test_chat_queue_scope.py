"""The paper chat's queue_task refuses a row of another paper before it takes
a snapshot or queues anything."""

import asyncio
from unittest.mock import patch

from agents.tool_context import ToolContext

from lib.agents.chat_agent import ChatRunContext, _make_queue_task_tool
from lib.models import FamilyDB, GeneDB, PaperDB
from lib.tasks.models import TaskDB


def _paper(db_session, content_hash):
    gene = db_session.query(GeneDB).first()
    if gene is None:
        gene = GeneDB(symbol='BRCA1')
        db_session.add(gene)
        db_session.flush()
    paper = PaperDB(content_hash=content_hash, gene_id=gene.id, filename='p.pdf')
    db_session.add(paper)
    db_session.flush()
    return paper


def _queue(paper_id, args):
    tool = _make_queue_task_tool(paper_id, 1)
    context = ChatRunContext()
    reply = asyncio.run(
        tool.on_invoke_tool(
            ToolContext(
                context=context,
                tool_name='queue_task',
                tool_call_id='call-1',
                tool_arguments=args,
            ),
            args,
        )
    )
    return reply, context


def test_a_family_of_another_paper_queues_nothing(db_session):
    paper = _paper(db_session, 'chat-scope-a')
    other = _paper(db_session, 'chat-scope-b')
    theirs = FamilyDB(
        paper_id=other.id,
        identifier='Family 1',
        identifier_evidence={'value': 'Family 1', 'reasoning': 'test'},
        consanguinity=False,
        consanguinity_evidence={'value': False, 'reasoning': 'test'},
    )
    db_session.add(theirs)
    # The tool reads and writes through a connection of its own.
    db_session.commit()

    with patch('lib.agents.chat_agent.write_snapshot_safe') as snapshot:
        reply, context = _queue(
            paper.id,
            f'{{"task_type": "Segregation Analysis Computed", "family_id": {theirs.id}}}',
        )

    assert reply == (
        f'Nothing was queued: This paper has no family {theirs.id}. Check the row '
        'with list_paper_entities and try again.'
    )
    # Not a confirmation, so the model, not the tool, answers the curator.
    assert context.confirmation is None
    snapshot.assert_not_called()
    db_session.expire_all()
    assert db_session.query(TaskDB).count() == 0
