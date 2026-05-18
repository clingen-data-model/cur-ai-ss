import json
from typing import Any

from agents import Agent, function_tool
from pydantic import BaseModel

from lib.api.db import session_scope
from lib.core.environment import env
from lib.models.family import FamilyDB
from lib.models.patient import PatientDB
from lib.models.phenotype import PhenotypeDB
from lib.models.variant import VariantDB
from lib.tasks.models import TaskDB, TaskType


class ChatRoutingOutput(BaseModel):
    task_id: int | None = None
    task_type: TaskType
    entity_label: str | None = None
    reasoning: str


_NON_CONVERSATIONAL = {
    TaskType.PDF_PARSING,
    TaskType.PAPER_ACKNOWLEDGEMENT,
    TaskType.VARIANT_ENRICHMENT,
}
_TASK_TYPE_LIST = '\n'.join(
    f'- "{t.value}": {t.description}' for t in TaskType if t not in _NON_CONVERSATIONAL
)

INSTRUCTIONS = f"""
You are a routing assistant for a genetic research paper analysis system.

Given a user question, follow these precise steps:

Step 1 — Identify the question's subject
Extract key entities (patient/family identifiers, variant descriptions, phenotypes) from the question.

Step 2 — Select the task type
Pick the most relevant task type from the list below:
{_TASK_TYPE_LIST}

Choose "{TaskType.GENERAL_PAPER_QUESTION}" if:
- The question spans multiple entities or agents (e.g. "summarize all variants")
- It's about variant annotations like gnomAD, SpliceAI, ClinVar, or allele frequencies
- It doesn't clearly match any other specific task type

Step 3 — Route the request
If you chose "{TaskType.GENERAL_PAPER_QUESTION}":
  → Return task_id=null with reasoning about why this is a cross-cutting question

Otherwise:
  → Call `fetch_tasks_for_type` with the chosen task type string
  → Examine all returned tasks and their entity_labels
  → Select the task whose entity_label best matches the question's subject

Step 4 — Validate your selection
Before returning, verify:
- Does the selected task's entity_label directly match the question's subject?
- Is the task_type the most specific match (not a default fallback)?
- Would this task actually answer the user's question?

If validation fails, reconsider your selection or choose GENERAL_PAPER_QUESTION as fallback.

Return:
- task_id: integer id of the chosen task, or null for "{TaskType.GENERAL_PAPER_QUESTION}"
- task_type: the task type string (e.g. "HPO Linking")
- entity_label: copy the entity_label from the chosen task exactly; null for global tasks
- reasoning: explain your routing choice, how the task matches the question, and any validation performed
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


def make_routing_agent(paper_id: int) -> Agent:
    fetch_tasks_for_type = _make_fetch_tasks_tool(paper_id)
    return Agent(
        name='chat_router',
        instructions=INSTRUCTIONS,
        model=env.OPENAI_API_DEPLOYMENT,
        output_type=ChatRoutingOutput,
        tools=[fetch_tasks_for_type],  # type: ignore[list-item]
    )
