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
from pydantic import BaseModel, Field

from lib.agents.model_factory import chat_model, chat_model_settings
from lib.api.db import session_scope
from lib.api.direct_edits import EditProblem, EditRequest, prepare_edits
from lib.api.entity_edits import variant_text
from lib.misc.snapshots import write_snapshot_safe
from lib.models.base import row_to_dict
from lib.models.chat_message import ChatProposal
from lib.models.family import FamilyDB
from lib.models.paper import PaperDB
from lib.models.patient import PatientDB
from lib.models.patient_variant_occurrences import PatientVariantOccurrenceDB
from lib.models.phenotype import PhenotypeDB
from lib.models.variant import VariantDB
from lib.tasks.flags import individual_label
from lib.tasks.handlers import (
    QA_UNSUPPORTED_TASK_TYPES,
    ask_task_agent,
    paper_citation_texts,
)
from lib.tasks.misc import (
    enqueue_all_instances,
    enqueue_task,
    infer_paper_status_detail,
    invalidate_descendants,
    notify_on_next_completion,
    paper_busy_message,
)
from lib.tasks.models import TaskDB, TaskResp, TaskStatus, TaskType

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
# Each step as task_type takes it, then the name curators know it by (the
# timeline and Rerun dialog show TaskType.label), so "re-run finding
# variants" resolves as readily as "re-run Variant Extraction".
_RUNNABLE_TASK_TYPE_LIST = '\n'.join(
    f'- "{t.value}" (shown to curators as "{t.label}"): {t.description}'
    for t in _RUNNABLE_TASK_TYPES
)

# Task types ask_task_agent can actually consult -- see QA_UNSUPPORTED_TASK_TYPES.
_ASKABLE_TASK_TYPES = [t for t in TaskType if t not in QA_UNSUPPORTED_TASK_TYPES]
_ASKABLE_TASK_TYPE_LIST = '\n'.join(
    f'- "{t.value}" (shown to curators as "{t.label}"): {t.description}'
    for t in _ASKABLE_TASK_TYPES
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


def _record(row: Any) -> dict:
    """A row's columns without its evidence blocks: the values, not the
    reasoning and citations behind each, which multiply a paper's records
    several times over and answer no question the record itself does not."""
    return {k: v for k, v in row_to_dict(row).items() if not k.endswith('_evidence')}


def _make_list_entities_tool(paper_id: int) -> Any:
    @function_tool
    def list_paper_entities() -> str:
        """List this paper's families, patients, variants, occurrences (which
        individual carries which variant) and phenotypes, every field but
        their evidence, so a row the user names can be matched on any of its
        fields. Every row has its ``id`` and a ``label``, the name the paper
        page and the edit card show it by ("Family 2 II-3", "Family 2 II-3:
        c.7696C>T"), with the family already joined in. Each variant also
        includes its harmonized and annotated records (the
        transcript-qualified HGVS lives there). Returns JSON."""
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
            occurrences = (
                session.query(PatientVariantOccurrenceDB)
                .filter(PatientVariantOccurrenceDB.paper_id == paper_id)
                .all()
            )

            def individual_name(patient: PatientDB) -> str:
                return individual_label(patient.family.identifier, patient.identifier)

            def variant_entry(variant: VariantDB) -> dict:
                entry = {'label': variant_text(variant), **_record(variant)}
                if variant.harmonized_variant is not None:
                    entry['harmonized_variant'] = _record(variant.harmonized_variant)
                if variant.annotated_variant is not None:
                    entry['annotated_variant'] = _record(variant.annotated_variant)
                return entry

            return json.dumps(
                {
                    'families': [
                        {'label': f.identifier, **_record(f)} for f in families
                    ],
                    'patients': [
                        {'label': individual_name(p), **_record(p)} for p in patients
                    ],
                    'variants': [variant_entry(v) for v in variants],
                    'occurrences': [
                        {
                            'label': f'{individual_name(o.patient)}: '
                            f'{variant_text(o.variant)}',
                            **_record(o),
                        }
                        for o in occurrences
                    ],
                    'phenotypes': [
                        {
                            'label': ph.concept,
                            'individual': individual_name(ph.patient),
                            **_record(ph),
                            'hpo_id': ph.hpo.hpo_id if ph.hpo else None,
                            'hpo_name': ph.hpo.hpo_name if ph.hpo else None,
                        }
                        for ph in phenotypes
                    ],
                },
                default=str,
            )

    return list_paper_entities


def _make_ask_extraction_agent_tool(paper_id: int) -> Any:
    @function_tool
    async def ask_extraction_agent(
        task_type: TaskType,
        question: str,
        family_id: int | None = None,
        patient_id: int | None = None,
        variant_id: int | None = None,
        phenotype_id: int | None = None,
        patient_variant_occurrence_id: int | None = None,
    ) -> str:
        """Ask the SAME agent that actually ran a given extraction step your
        question, in its own conversation -- grounded in exactly what it
        considered (including its own tool calls), not a guess from the
        current database state. Use this for any "why"/"how" question about a
        specific step's reasoning (e.g. "why did variant extraction call this
        a frameshift?", "why didn't HPO linking match this phenotype?").

        task_type MUST be one of the askable types listed in your instructions.

        For an entity-scoped step, first call list_paper_entities and pass the
        matched row's id in the right field (family_id/patient_id/
        variant_id/phenotype_id/patient_variant_occurrence_id) -- the same
        scope enqueue_task uses. Leave every id null for a paper-wide step.
        Returns the agent's answer, or a message explaining why none is
        available (step hasn't run yet, or has no conversation to consult)."""
        if task_type in QA_UNSUPPORTED_TASK_TYPES:
            return f'"{task_type.label}" has no agent conversation to consult.'

        with session_scope() as session:
            task = (
                session.query(TaskDB)
                .filter(
                    TaskDB.type == task_type,
                    TaskDB.paper_id == paper_id,
                    TaskDB.family_id == family_id,
                    TaskDB.patient_id == patient_id,
                    TaskDB.variant_id == variant_id,
                    TaskDB.phenotype_id == phenotype_id,
                    TaskDB.patient_variant_occurrence_id
                    == patient_variant_occurrence_id,
                )
                .first()
            )
            if task is None:
                return f'No "{task_type.label}" step found for that scope.'
            task_id = task.id

        return await ask_task_agent(task_id, task_type, paper_id, question)

    return ask_extraction_agent


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
        type, first call list_paper_entities and pass the matched row's id in
        the right field, plus its label as entity_label. If
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

            busy = paper_busy_message(session, paper_id, 're-running')
            if busy:
                return busy

            # See create_task's identical call in lib/api/app.py: a rerun's
            # handlers delete-and-recreate rows, which would otherwise
            # silently discard any manual edit made since the last snapshot.
            write_snapshot_safe(
                session, paper_id, description=f'Before re-run: {task_type.label}'
            )

            notify_on_next_completion(session, paper_id, user_id)

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
            if len(tasks) == 1 and tasks[0].status == TaskStatus.RUNNING:
                # Already in flight; enqueue_task left it unchanged, so any new
                # guidance was not applied -- don't claim it was.
                confirmation = (
                    f'"{task_type.label}"{target} is already in progress. '
                    f'Results will appear on the paper page when it finishes.'
                )
            else:
                guidance = (
                    f' with your guidance: "{additional_context}"'
                    if additional_context
                    else ''
                )
                confirmation = (
                    f'Queued "{task_type.label}"{target}{guidance}. It will '
                    f'run shortly and results will appear on the paper page.'
                )
        ctx.context.confirmation = confirmation
        return confirmation

    return queue_task


class ChatReply(BaseModel):
    """The chat's answer to one message. ``edits`` is set only for a direct
    edit the model could express; the API checks them and, when they pass,
    shows them for the curator to confirm (lib.api.direct_edits)."""

    message: str = Field(
        description='What to say to the user. For a direct edit you could '
        'express, one short line introducing the edits; for one you could '
        'not, why not and what they can do next.'
    )
    edits: list[EditRequest] = Field(
        default_factory=list,
        description='The direct edits the user asked for, or empty.',
    )
    note: str = Field(
        default='',
        description='With edits: one plain line saying what the curator asked '
        'for, naming each row by its label ("Set F7285 IV:3 to male."). It is '
        "recorded on every edit, ahead of the curator's own messages. Empty "
        'without edits.',
    )
    request_messages: int = Field(
        default=1,
        ge=1,
        description="With edits: how many of the curator's most recent "
        'messages, counting this one, make up the request: 1 when this message '
        'asks for the edits on its own; more when it continues one earlier in '
        'the chat ("make IV:3 a male", "the latter", "try again" is 3). Leave '
        'out earlier messages about something else.',
    )


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
  - Pick a task_type. It MUST be one of these runnable types, given as the
    value in quotes; curators may name a step either way, so match their
    words against both names. When you name a step to the curator, use the
    name they are shown:
{_RUNNABLE_TASK_TYPE_LIST}
  - If the request clearly targets one entity (a patient/family label, or any
    variant identifier), call list_paper_entities and match the user's words
    against each row's label and fields -- users never know internal ids.
    Use the matched row's id in the right field (family_id/patient_id/variant_id/phenotype_id/
    patient_variant_occurrence_id) and pass its label as entity_label. If
    nothing matches, or two rows match equally, ask which they mean instead
    of guessing.
  - If the request is paper-wide (no entity named), call queue_task with every
    entity id left null.
  - Pass any extra guidance as additional_context.
  - Call queue_task, then reply with exactly its return value and nothing else.

DIRECT EDITS
If the user wants to change the data themselves -- add, remove or change a
family, an individual, a variant, an occurrence or a phenotype ("add
seizures to II-1", "II-3 is female", "remove the c.123A>G variant", "II-1 is
homozygous for it", "add Family 4") -- this is a DIRECT EDIT, not an
ACTION. Never queue a task for it, and never queue a task as well: a
re-run reads the paper again and replaces what it wrote, which is a
different thing from the curator changing one value.
  - Resolve every row the request names with list_paper_entities, as for an
    ACTION. If the request is ambiguous (which individual, in a paper with
    several families; which of two similar variants), ask instead of
    guessing.
  - A phenotype is added without an HPO term; never pick one. To link or
    relink one, the curator uses the HPO picker on the paper page, or asks
    for HPO linking to be re-run, which is an ACTION.
  - Evidence comes from the curator only. When their message quotes the
    paper as the edit's evidence ("... -- the paper says 'had recurrent
    seizures from age two'"), pass that quote, copied exactly from their
    message. When it gives none, leave quote empty: never find, write or
    paraphrase evidence yourself. If they ask for a citation without giving
    the sentence, ask them for it.
  - Put the edits in ``edits``, every edit of the request; one short line
    introducing them in ``message``; and in ``note`` one plain line saying
    what the curator asked for, naming rows by label ("Set F7285 IV:3 to
    male."), which every edit records ahead of the curator's own messages;
    and in ``request_messages`` how many of the curator's recent messages,
    this one included, the request is made of. They are checked, then shown to
    the curator to confirm; nothing is changed until they do, so never say
    the edits are made.
  - When you cannot express the request as edits -- it is ambiguous, it
    names a row that does not exist, it needs a row the same request would
    create (a new family and an individual in it), or it asks for something
    listed below as not available -- leave ``edits`` empty and say in
    ``message`` why, and what the curator can do next (which row they mean;
    to add the family first and then the individual; to use the paper page).
    Never add an edit the curator did not ask for.

  Each edit names an entity and an action. update and delete take
  entity_id, the row's id from list_paper_entities; create takes parent_id
  where the row belongs to another. ``values`` are the fields to set, by
  their names in list_paper_entities, each a string, number, boolean or
  (testing_methods) list of strings; a choice must be one of its allowed
  values. On an update, send only the fields whose value changes: a field
  that already holds the value (a unit that stays the same beside a new
  age) is left out.
    family: create (identifier, optionally consanguinity), update
      (identifier, consanguinity), delete (only once it has no individuals:
      otherwise tell the curator to delete all individuals in the family
      first).
    patient (an individual): create (parent_id = the family's id;
      identifier, and any demographics; the rest default to Unknown), update
      (any demographic field), delete (also removes their occurrences and
      phenotypes).
    variant: create (at least one of variant, hgvs_c, hgvs_p, hgvs_g, rsid;
      any other descriptive field), update (variant_type,
      functional_evidence, main_focus, and the harmonized fields hgvs_c,
      hgvs_p, hgvs_g, rsid, caid, gnomad_style_coordinates), delete (also
      removes its occurrences).
    occurrence (an individual carrying a variant): create (parent_id = the
      individual's id; variant_id, and optionally zygosity, inheritance,
      variant_inheritance, testing_methods (at most two), disease_name),
      update (those same fields), delete.
    phenotype: create (parent_id = the individual's id; concept only), and
      delete. Not available: changing its HPO term.

QUESTIONS
Otherwise, answer using the PAPER CONTEXT block. Call list_paper_entities only
when you need fuller detail than the summary gives (e.g. harmonized/annotated
variant records). If the context doesn't contain the answer, say so rather
than guessing.

For a "why"/"how" question about a specific extraction step's reasoning (e.g.
"why did variant extraction call this a frameshift?", "why didn't HPO linking
match this phenotype?"), don't guess from the PAPER CONTEXT block or the
current data alone -- call ask_extraction_agent so the actual agent that did
that work answers from its own memory of what it considered. task_type MUST
be one of these askable types:
{_ASKABLE_TASK_TYPE_LIST}
Resolve an entity-scoped question's target the same way as an ACTION (call
list_paper_entities, match it, pass the matched id). If it returns
that no task/conversation is available, say so rather than falling back to a
guess.

Whatever the request, your reply to the user goes in ``message``. Name rows
there as the paper page does, by label ("F7285 IV:3", a variant as the paper
writes it), never by id, and call a patient an individual. Keep it
short and conversational -- this is a chat panel, not a report.
"""


def make_chat_agent(paper_id: int, user_id: int) -> Agent:
    """One agent per chat turn, answering with a ``ChatReply``. For a
    QUESTION its message is the answer. For an ACTION it calls queue_task,
    which enqueues the task (attributed to user_id) and records a
    confirmation on the run context; the caller treats a populated
    ``ChatRunContext.confirmation`` as "a task was queued" and uses that
    text verbatim as the assistant's reply. For a DIRECT EDIT its edits are
    checked and proposed by the caller (lib.api.direct_edits.propose).
    """
    return Agent(
        name='chat_agent',
        instructions=CHAT_AGENT_INSTRUCTIONS,
        model=chat_model(),
        model_settings=chat_model_settings(),
        output_type=ChatReply,
        tools=[  # type: ignore[list-item]
            _make_list_entities_tool(paper_id),
            _make_ask_extraction_agent_tool(paper_id),
            _make_queue_task_tool(paper_id, user_id),
        ],
    )
