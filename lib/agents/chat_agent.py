"""Per-paper chat: answers questions about a paper and can queue pipeline tasks.

Rebuilds the feature dropped in 53040115. That version depended on OpenAI's
server-side conversation_id (see lib/tasks/agent_session.py's docstring);
this one runs on the same provider-agnostic SQLiteSession every task uses
(lib.tasks.agent_session.chat_session), so one Runner.run() per message
suffices -- no separate classify-then-answer split. Action-vs-question
detection happens inside that single call, via the queue_task tool, exactly
as it did in the deleted lib/agents/chat_routing_agent.py.
"""

import json
from dataclasses import dataclass
from typing import Any

from agents import Agent, RunContextWrapper, function_tool

from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
from lib.agents.model_factory import chat_model, chat_model_settings
from lib.api.db import session_scope
from lib.misc.snapshots import write_snapshot_safe
from lib.models.base import row_to_dict
from lib.models.family import FamilyDB
from lib.models.paper import PaperDB
from lib.models.patient import PatientDB
from lib.models.phenotype import PhenotypeDB
from lib.models.variant import VariantDB
from lib.tasks.misc import (
    enqueue_all_instances,
    enqueue_task,
    infer_paper_status_detail,
    invalidate_descendants,
)
from lib.tasks.models import CLAIMED_STATUSES, TaskDB, TaskResp, TaskType

# Excluded from chat-triggered reruns: PDF parsing and paper classification
# run before there is any extracted data to chat about, and variant
# annotation is a purely mechanical enrichment step with nothing to discuss
# or misconfigure. Everything else is fair game.
_NOT_CHAT_RUNNABLE = {
    TaskType.PDF_PARSING,
    TaskType.PAPER_CLASSIFIER,
    TaskType.VARIANT_ANNOTATION,
}
_RUNNABLE_TASK_TYPES = [t for t in TaskType if t not in _NOT_CHAT_RUNNABLE]
_RUNNABLE_TASK_TYPE_LIST = '\n'.join(
    f'- "{t.value}": {t.description}' for t in _RUNNABLE_TASK_TYPES
)


@dataclass
class ChatRunContext:
    """Run context for a chat turn. The ``queue_task`` tool stores its
    confirmation here, built from the real queued task -- so the API can use
    that exact text as the assistant's reply instead of letting the model
    paraphrase (and risk misstating) what it just did."""

    confirmation: str | None = None


def build_paper_chat_context(paper_id: int) -> str:
    """A snapshot of the paper's current extracted state, as JSON.

    Sent fresh with every user turn rather than baked once into the system
    instructions: extraction can finish, or a queued task can complete,
    between chat turns, so a stale snapshot would make chat contradict what
    the user sees on the paper page.
    """
    with session_scope() as session:
        paper = session.get(PaperDB, paper_id)
        if paper is None:
            return json.dumps({'error': f'Paper {paper_id} not found'})

        patients = session.query(PatientDB).filter(PatientDB.paper_id == paper_id).all()
        variants = session.query(VariantDB).filter(VariantDB.paper_id == paper_id).all()
        phenotypes = (
            session.query(PhenotypeDB).filter(PhenotypeDB.paper_id == paper_id).all()
        )
        tasks = session.query(TaskDB).filter(TaskDB.paper_id == paper_id).all()

        context = {
            'paper': {
                'id': paper.id,
                'title': paper.title,
                'first_author': paper.first_author,
                'journal_name': paper.journal_name,
                'publication_year': paper.publication_year,
                'gene_symbol': paper.gene.symbol if paper.gene else None,
            },
            'patients': [
                {
                    'id': p.id,
                    'identifier': p.identifier,
                    'proband_status': p.proband_status,
                    'sex': p.sex,
                    'affected_status': p.affected_status,
                }
                for p in patients
            ],
            'variants': [
                {
                    'id': v.id,
                    'variant': v.variant,
                    'hgvs_c': v.hgvs_c,
                    'hgvs_p': v.hgvs_p,
                }
                for v in variants
            ],
            'phenotype_count': len(phenotypes),
            'pipeline_status': infer_paper_status_detail(
                [TaskResp.model_validate(t, from_attributes=True) for t in tasks]
            ),
        }
        return json.dumps(context, default=str)


def _make_list_entities_tool(paper_id: int) -> Any:
    @function_tool
    def list_paper_entities() -> str:
        """List this paper's families, patients, variants, and phenotypes as
        full records, so an entity the user names can be matched on any of
        its fields. Each variant also includes its harmonized and annotated
        records (the transcript-qualified HGVS lives there). Use the
        top-level ``id`` of the matched entity when queueing a task. Returns
        JSON."""
        with session_scope() as session:
            families = (
                session.query(FamilyDB).filter(FamilyDB.paper_id == paper_id).all()
            )
            patients = (
                session.query(PatientDB).filter(PatientDB.paper_id == paper_id).all()
            )
            variants = (
                session.query(VariantDB).filter(VariantDB.paper_id == paper_id).all()
            )
            phenotypes = (
                session.query(PhenotypeDB)
                .filter(PhenotypeDB.paper_id == paper_id)
                .all()
            )

            def variant_entry(variant: VariantDB) -> dict:
                entry = row_to_dict(variant)
                if variant.harmonized_variant is not None:
                    entry['harmonized_variant'] = row_to_dict(
                        variant.harmonized_variant
                    )
                if variant.annotated_variant is not None:
                    entry['annotated_variant'] = row_to_dict(variant.annotated_variant)
                return entry

            return json.dumps(
                {
                    'families': [row_to_dict(f) for f in families],
                    'patients': [row_to_dict(p) for p in patients],
                    'variants': [variant_entry(v) for v in variants],
                    'phenotypes': [row_to_dict(ph) for ph in phenotypes],
                },
                default=str,
            )

    return list_paper_entities


def _make_queue_task_tool(paper_id: int, user_id: int) -> Any:
    @function_tool
    def queue_task(
        ctx: RunContextWrapper[ChatRunContext],
        task_type: TaskType,
        entity_label: str | None = None,
        family_id: int | None = None,
        patient_id: int | None = None,
        variant_id: int | None = None,
        phenotype_id: int | None = None,
        patient_variant_occurrence_id: int | None = None,
        additional_context: str | None = None,
        skip_successors: bool = False,
    ) -> str:
        """Queue an extraction/analysis task for this paper, mirroring what
        the "Rerun Agents" button does. Leave every entity id null to queue
        every instance of a paper-wide task type. For an entity-specific task
        type, first call list_paper_entities and pass the matched entity's
        top-level id in the right field, plus its label as entity_label. If
        the user gave extra guidance for the rerun (e.g. "treat patient 3 as
        the proband"), pass it as additional_context. Returns a user-facing
        confirmation -- reply with exactly that text."""
        if task_type not in _RUNNABLE_TASK_TYPES:
            return f'"{task_type}" is not a runnable task; answer it as a question instead.'

        no_scope = (
            family_id is None
            and patient_id is None
            and variant_id is None
            and phenotype_id is None
            and patient_variant_occurrence_id is None
        )
        with session_scope() as session:
            paper = session.get(PaperDB, paper_id)
            if paper is None:
                return 'This paper no longer exists.'

            # See create_task's identical call in lib/api/app.py: a rerun's
            # handlers delete-and-recreate rows, which would otherwise
            # silently discard any manual edit made since the last snapshot.
            write_snapshot_safe(
                session, paper_id, description=f'Before re-running {task_type.value}'
            )

            if not skip_successors:
                invalidate_descendants(session, paper_id, task_type)

            if no_scope:
                tasks = enqueue_all_instances(
                    session,
                    paper_id=paper_id,
                    task_type=task_type,
                    skip_successors=skip_successors,
                    additional_context=additional_context,
                    updated_by_user_id=user_id,
                )
            else:
                tasks = [
                    enqueue_task(
                        session,
                        paper_id=paper_id,
                        task_type=task_type,
                        family_id=family_id,
                        patient_id=patient_id,
                        variant_id=variant_id,
                        phenotype_id=phenotype_id,
                        patient_variant_occurrence_id=patient_variant_occurrence_id,
                        additional_context=additional_context,
                        skip_successors=skip_successors,
                        updated_by_user_id=user_id,
                    )
                ]

            target = f' for "{entity_label}"' if entity_label else ''
            if len(tasks) == 1 and tasks[0].status in CLAIMED_STATUSES:
                # Already in flight; enqueue_task left it unchanged, so any new
                # guidance was not applied -- don't claim it was.
                confirmation = (
                    f'The "{task_type}" task{target} is already in progress. '
                    f'Results will appear on the paper page when it finishes.'
                )
            else:
                guidance = (
                    f' with your guidance: "{additional_context}"'
                    if additional_context
                    else ''
                )
                confirmation = (
                    f'Queued the "{task_type}" task{target}{guidance}. It will '
                    f'run shortly and results will appear on the paper page.'
                )
        ctx.context.confirmation = confirmation
        return confirmation

    return queue_task


CHAT_AGENT_INSTRUCTIONS = f"""
You are a genomics-curation assistant embedded in a paper's chat panel.

Every user message arrives prefixed with a "PAPER CONTEXT" JSON block --
a snapshot of this paper's current extracted patients, variants, phenotype
count, and pipeline status. It reflects the database as of this message, not
necessarily what an earlier turn discussed, so trust it over anything said
previously in the conversation.

ACTIONS
If the user wants to RUN, RE-RUN, QUEUE, REQUEUE, regenerate, or refresh an
extraction/analysis step (e.g. "re-run variant extraction", "redo phenotype
extraction for patient III-2"), this is an ACTION even when the message also
contains extra guidance -- a phrase like "re-run X but treat Y" is one action
with Y as additional_context, not a separate question.
  - Pick a task_type. It MUST be one of these runnable types:
{_RUNNABLE_TASK_TYPE_LIST}
  - If the request clearly targets one entity (a patient/family label, or any
    variant identifier), call list_paper_entities and match it against any
    field of the returned records -- users never know internal ids. Use the
    matched entity's top-level id in the right field (family_id/patient_id/
    variant_id/phenotype_id/patient_variant_occurrence_id) and pass its label
    as entity_label. If nothing clearly matches, ask which entity they mean
    instead of guessing.
  - If the request is paper-wide (no entity named), call queue_task with every
    entity id left null.
  - Pass any extra guidance as additional_context.
  - Call queue_task, then reply with exactly its return value and nothing else.

QUESTIONS
Otherwise, answer using the PAPER CONTEXT block. Call list_paper_entities only
when you need fuller detail than the summary gives (e.g. harmonized/annotated
variant records). If the context doesn't contain the answer, say so rather
than guessing.

Keep replies short and conversational -- this is a chat panel, not a report.
"""


def make_chat_agent(paper_id: int, user_id: int) -> Agent:
    """One agent per chat turn. For a QUESTION it answers in prose. For an
    ACTION it calls queue_task, which enqueues the task (attributed to
    user_id) and records a confirmation on the run context; the caller
    treats a populated ``ChatRunContext.confirmation`` as "a task was queued"
    and uses that text verbatim as the assistant's reply.
    """
    return Agent(
        name='chat_agent',
        instructions=BASE_SYSTEM_INSTRUCTIONS,
        model=chat_model(),
        model_settings=chat_model_settings(),
        tools=[  # type: ignore[list-item]
            _make_list_entities_tool(paper_id),
            _make_queue_task_tool(paper_id, user_id),
        ],
    )
