import json

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
    task_id: int
    task_type: TaskType
    entity_label: str | None = None


_TASK_TYPE_LIST = '\n'.join(f'- "{t.value}": {t.description}' for t in TaskType)

INSTRUCTIONS = f"""
You are a routing assistant for a genetic research paper analysis system.

Given a user question, follow these two steps:

Step 1 — Pick the most relevant task type string from the list below based on the question topic:
{_TASK_TYPE_LIST}

Step 2 — Call `fetch_tasks_for_type` with the task type string chosen above.
From the returned JSON list of tasks, each entry includes an `entity_label` field computed
from the entity (patient identifier, variant HGVS, or phenotype concept). Select the task
whose entity_label best matches the subject of the user's question.

Return:
- task_id: the integer id of the chosen task
- task_type: the task type string (e.g. "HPO Linking")
- entity_label: copy the entity_label value from the chosen task exactly as returned by the tool
  (do not generate or modify it); null for global tasks
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


def _make_fetch_tasks_tool(paper_id: int):
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
