import json
from dataclasses import dataclass
from typing import Any

from agents import Agent, RunContextWrapper, function_tool
from pydantic import BaseModel

from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
from lib.api.db import session_scope
from lib.core.environment import env
from lib.models.base import row_to_dict
from lib.models.family import FamilyDB
from lib.models.patient import PatientDB
from lib.models.phenotype import PhenotypeDB
from lib.models.variant import VariantDB
from lib.tasks.misc import enqueue_task
from lib.tasks.models import TaskDB, TaskStatus, TaskType


class ChatRoutingOutput(BaseModel):
    task_id: int | None = None
    task_type: TaskType
    entity_label: str | None = None
    reasoning: str


@dataclass
class ChatRunContext:
    """Run context for a chat turn. The ``queue_task`` tool stores its confirmation
    here, built from the real task, so the API can surface it — and treat a non-None
    ``confirmation`` as the signal that a task was queued."""

    confirmation: str | None = None


# Task types that have no chat conversation to route questions to: PDF parsing and
# paper classification run before any chat is possible, and variant annotation is a
# purely mechanical enrichment step with nothing to discuss. Excluded from routing.
_NON_CONVERSATIONAL = {
    TaskType.PDF_PARSING,
    TaskType.PAPER_CLASSIFIER,
    TaskType.VARIANT_ANNOTATION,
}
# Task types that operate on the paper as a whole rather than a single entity. The
# router returns no entity (task_id/entity_label null) when it picks one of these.
_GLOBAL_AGENTS = {
    TaskType.GENERAL_PAPER_QUESTION,
    TaskType.PAPER_METADATA,
    TaskType.VARIANT_EXTRACTION,
    TaskType.PEDIGREE_DESCRIPTION,
    TaskType.PATIENT_EXTRACTION,
    TaskType.PATIENT_VARIANT_OCCURRENCES,
}
# Task types a chat QUESTION can be routed to (everything with a conversation to
# answer from). Rendered into the routing instructions and used to validate output.
_CONVERSATIONAL_TASK_TYPES = [t for t in TaskType if t not in _NON_CONVERSATIONAL]
_TASK_TYPE_LIST = '\n'.join(
    f'- "{t.value}": {t.description}' for t in _CONVERSATIONAL_TASK_TYPES
)

# Task types a user can queue from chat. General Paper Question is a chat-only
# pseudo-task (answered live), not something the worker runs, so it is excluded.
_RUNNABLE_TASK_TYPES = [
    t for t in _CONVERSATIONAL_TASK_TYPES if t != TaskType.GENERAL_PAPER_QUESTION
]
_RUNNABLE_TASK_TYPE_LIST = '\n'.join(
    f'- "{t.value}": {t.description}' for t in _RUNNABLE_TASK_TYPES
)

CHAT_ROUTING_INSTRUCTIONS = f"""Handle a user's chat message about a genomics paper. The message is
either an ACTION (run something) or a QUESTION (route it to be answered).

Step 0 — Action vs. question
If the user wants to RUN, RE-RUN, QUEUE, REQUEUE, regenerate, or refresh an extraction/analysis agent
(e.g. "re-run variant extraction", "extract phenotypes for patient III-2 again",
 "requeue the patient extraction and include all patients from the pedigree"):
  **This is an ACTION even when the message also contains instructions or extra context.**
  A phrase like "requeue X and include Y" or "re-run X this time with Y" is an ACTION where
  the second clause is additional_context for the task — it is NOT a question about Y.
  → Pick the task_type. It MUST be one of these runnable task types (NOT "General Paper Question"):
{_RUNNABLE_TASK_TYPE_LIST}
  → For GLOBAL task types (Patient Extraction, Variant Extraction, Paper Metadata, Pedigree
    Description, Patient Variant Linking): do NOT call list_paper_entities. Call `queue_task`
    directly with no entity IDs.
  → For entity-specific task types, call `list_paper_entities` (full records, including each
    variant's harmonized and annotated records). Match the entity the user named against any
    field of the returned records — users reference entities by whatever identifier they have
    (a patient/family label, or any variant identifier), never internal ids. If no record
    clearly matches, do not guess: ask the user which entity they mean instead of queueing.
  → Call the `queue_task` tool with the task_type, the matched entity's top-level id in the right
    field (family_id/patient_id/variant_id/phenotype_id), and a human-readable label for it as
    entity_label.
  → If the user gives extra guidance for the rerun (e.g. "this time treat patient 3 as the
    proband", "include all patients from the pedigree"), pass it as additional_context.
  → Then return task_type="General Paper Question", task_id=null, entity_label=null,
    reasoning="queued" (the queue result is used directly; this output is ignored).
Otherwise the message is a QUESTION — route it using the steps below.

Step 1 — Identify the question's subject
Extract key entities (patient/family identifiers, variant descriptions, phenotypes) from the question.

Step 2 — Select the task type
Pick the most relevant task type from the list below. Use EXACTLY one of these values for task_type:
{_TASK_TYPE_LIST}

**Important: Agent scopes**
- **Global agents** perform extraction/analysis at the paper level without associated entity IDs:
  Patient Extraction, Variant Extraction, Paper Metadata, Pedigree Description, Patient Variant Linking,
  General Paper Question. These work on the paper as a whole.

- **Entity-specific agents** operate on a specific entity instance and require routing to a matched entity:
  Segregation Evidence Extraction (per-family), Segregation Analysis Computed (per-family),
  Variant Harmonization (per-variant), Patient Demographics (per-patient),
  Phenotype Extraction (per-patient), HPO Linking (per-phenotype).

Step 3 — Route the request
**Critical distinction for global agents:**
- Questions ABOUT VARIANTS (why weren't they extracted, how were they processed, etc.) → "Variant Extraction"
- Questions ABOUT PATIENT IDENTITY (which patients exist, identifiers, proband status, family grouping) → "Patient Extraction"
- Questions ABOUT PATIENT DEMOGRAPHICS (sex, age, race, ethnicity, country of origin, affected status, carrier status, relationship to proband, twin status) → "Patient Demographics" (per-patient; match the relevant patient)
- Questions ABOUT PEDIGREES (pedigree images/diagrams, family structure visualization, etc.) → "Pedigree Description"
- Questions ABOUT PATIENT-VARIANT LINKS (inheritance, segregation, testing, etc.) → "Patient Variant Linking"
- Questions ABOUT PAPER METADATA (title, authors, publication date, etc.) → "Paper Metadata"
- General questions that don't fit above categories (overall summary, general discussion, etc.) → "General Paper Question"

If you chose "General Paper Question":
  → Return task_id=null, entity_label=null
  → Reasoning: explain why this task is paper-wide and doesn't fit the more specific categories

For all other task types:
  → Call `fetch_tasks_for_type` with the chosen task type string (MUST match one of the exact values above)
  → Examine all returned tasks and their entity_labels
  → If the task type is entity-specific (per-family, per-patient, per-variant, per-phenotype):
     Select the task whose entity_label best matches the question's subject
  → Return the task_id and entity_label from the matched task

Step 4 — Validate your selection
Before returning, verify:
- Is the task_type one of the exact values listed above?
- If "General Paper Question": Does the question genuinely NOT relate to variants, patients, families, links, or metadata?
- For all other types: Did fetch_tasks_for_type return at least one result?
- If entity-specific: Does the selected task's entity_label match the question's subject?
- Would this task actually answer the user's question?

If validation fails, reconsider your selection or choose "General Paper Question" as fallback.

Return:
- task_id: integer id of the chosen task, or null for global agents
- task_type: MUST be one of the exact values listed above
- entity_label: the entity identifier from the matched task; null for global agents
- reasoning: explain your routing choice, agent scope classification, entity matching, and validation
"""


def _entity_label(
    family: FamilyDB | None,
    patient: PatientDB | None,
    variant: VariantDB | None,
    phenotype: PhenotypeDB | None,
) -> str | None:
    if family:
        return family.identifier
    if patient:
        return patient.identifier
    if variant:
        return variant.hgvs_c or variant.variant
    if phenotype:
        return phenotype.concept
    return None


def _make_fetch_tasks_tool(paper_id: int) -> Any:
    @function_tool
    def fetch_tasks_for_type(task_type: str) -> str:
        """Fetch all completed tasks for this paper that match a given task type.
        Each entry includes an entity_label (patient identifier, variant HGVS, or phenotype concept).
        Returns a JSON array of matching tasks."""
        with session_scope() as session:
            rows = (
                session.query(TaskDB, FamilyDB, PatientDB, VariantDB, PhenotypeDB)
                .outerjoin(FamilyDB, TaskDB.family_id == FamilyDB.id)
                .outerjoin(PatientDB, TaskDB.patient_id == PatientDB.id)
                .outerjoin(VariantDB, TaskDB.variant_id == VariantDB.id)
                .outerjoin(PhenotypeDB, TaskDB.phenotype_id == PhenotypeDB.id)
                .filter(TaskDB.paper_id == paper_id, TaskDB.type == task_type)
                .all()
            )
            results = []
            for task, family, patient, variant, phenotype in rows:
                if not task.conversation_id:
                    continue
                entry: dict = {
                    'task_id': task.id,
                    'type': task.type,
                    'status': task.status,
                    'entity_label': _entity_label(family, patient, variant, phenotype),
                }
                if family:
                    entry['family'] = {'id': family.id, 'identifier': family.identifier}
                if patient:
                    entry['patient'] = {
                        'id': patient.id,
                        'identifier': patient.identifier,
                        'proband_status': patient.proband_status,
                        'sex': patient.sex,
                        'age_diagnosis': patient.age_diagnosis,
                    }
                if variant:
                    entry['variant'] = {
                        'id': variant.id,
                        'variant': variant.variant,
                        'hgvs_c': variant.hgvs_c,
                        'hgvs_p': variant.hgvs_p,
                        'hgvs_g': variant.hgvs_g,
                    }
                if phenotype:
                    entry['phenotype'] = {
                        'id': phenotype.id,
                        'concept': phenotype.concept,
                        'negated': phenotype.negated,
                        'onset': phenotype.onset,
                    }
                results.append(entry)

            return json.dumps(results)

    return fetch_tasks_for_type


def _make_list_entities_tool(paper_id: int) -> Any:
    @function_tool
    def list_paper_entities() -> str:
        """List this paper's families, patients, variants, and phenotypes as full records,
        so an entity the user names can be matched on any of its fields. Each variant also
        includes its harmonized and annotated records (the transcript-qualified HGVS lives
        there). Use the top-level ``id`` of the matched entity when queueing. Returns JSON."""
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
        additional_context: str | None = None,
        skip_successors: bool = False,
    ) -> str:
        """Queue an extraction/analysis task for this paper, optionally scoped to one entity.
        Use entity ids from `list_paper_entities`; pass that entity's label as entity_label.
        If the user gives extra guidance for the rerun (e.g. "this time treat patient 3 as the
        proband"), pass it as additional_context; the rerun continues the prior conversation
        with that guidance instead of starting fresh. Returns a user-facing confirmation."""
        if task_type not in _RUNNABLE_TASK_TYPES:
            # Not a runnable pipeline task (e.g. General Paper Question) — don't queue;
            # leave confirmation unset so the message is handled as a question instead.
            return f'"{task_type}" is not a runnable task; answer it as a question instead.'
        with session_scope() as session:
            task = enqueue_task(
                session,
                paper_id=paper_id,
                task_type=task_type,
                family_id=family_id,
                patient_id=patient_id,
                variant_id=variant_id,
                phenotype_id=phenotype_id,
                additional_context=additional_context,
                skip_successors=skip_successors,
                updated_by_user_id=user_id,
            )
            # Build the confirmation from the real task while the session is open.
            target = f' for "{entity_label}"' if entity_label else ''
            if task.status in (TaskStatus.RUNNING, TaskStatus.QUEUED):
                # Already in flight; enqueue_task left it unchanged, so any new
                # guidance was not applied — don't claim it was.
                confirmation = (
                    f'The "{task.type}" task{target} is already '
                    f'{task.status.value.lower()}. Results will appear on the paper '
                    f'page when it finishes.'
                )
            else:
                guidance = (
                    f' with your guidance: "{additional_context}"'
                    if additional_context
                    else ''
                )
                confirmation = (
                    f'Queued the "{task.type}" task{target}{guidance}. It will run '
                    f'shortly and results will appear on the paper page.'
                )
        ctx.context.confirmation = confirmation
        return confirmation

    return queue_task


# --- Agent ------------------------------------------------------------------


def make_routing_agent(paper_id: int, user_id: int) -> Agent:
    """Single chat agent. For a QUESTION it returns a ``ChatRoutingOutput`` selecting the
    task conversation (or General QA) to answer from. For an ACTION it calls the
    ``queue_task`` tool, which enqueues the task (attributed to ``user_id``) and records a
    confirmation in the run context; the API treats a populated
    ``ChatRunContext.confirmation`` as "a task was queued" and ignores the routing output.
    """
    return Agent(
        name='chat_router',
        instructions=BASE_SYSTEM_INSTRUCTIONS,
        model=env.OPENAI_API_DEPLOYMENT,
        output_type=ChatRoutingOutput,
        tools=[  # type: ignore[list-item]
            _make_fetch_tasks_tool(paper_id),
            _make_list_entities_tool(paper_id),
            _make_queue_task_tool(paper_id, user_id),
        ],
    )
