import json
from typing import Any

from agents import Agent, function_tool
from pydantic import BaseModel

from lib.agents.base_instructions import BASE_SYSTEM_INSTRUCTIONS
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
    TaskType.PAPER_CLASSIFIER,
    TaskType.VARIANT_ANNOTATION,
}
_GLOBAL_AGENTS = {
    TaskType.GENERAL_PAPER_QUESTION,
    TaskType.PAPER_METADATA,
    TaskType.VARIANT_EXTRACTION,
    TaskType.PEDIGREE_DESCRIPTION,
    TaskType.PATIENT_EXTRACTION,
    TaskType.PATIENT_VARIANT_LINKING,
}
_CONVERSATIONAL_TASK_TYPES = [t for t in TaskType if t not in _NON_CONVERSATIONAL]
_TASK_TYPE_LIST = '\n'.join(
    f'- "{t.value}": {t.description}' for t in _CONVERSATIONAL_TASK_TYPES
)
_VALID_TASK_TYPE_VALUES = [t.value for t in _CONVERSATIONAL_TASK_TYPES]

CHAT_ROUTING_INSTRUCTIONS = f"""Given a user question about a genomics paper, route to the appropriate task type.

Step 1 — Identify the question's subject
Extract key entities (patient/family identifiers, variant descriptions, phenotypes) from the question.

Step 2 — Select the task type
Pick the most relevant task type from the list below. Use EXACTLY one of these values for task_type:
{_TASK_TYPE_LIST}

**IMPORTANT: task_type must be one of these exact values:
{chr(10).join(f'  - "{v}"' for v in _VALID_TASK_TYPE_VALUES)}

**Important: Agent scopes**
- **Global agents** perform extraction/analysis at the paper level without associated entity IDs:
  Patient Extraction, Variant Extraction, Paper Metadata, Pedigree Description, Patient Variant Linking,
  General Paper Question. These work on the paper as a whole.

- **Entity-specific agents** operate on a specific entity instance and require routing to a matched entity:
  Segregation Evidence Extraction (per-family), Segregation Analysis Computed (per-family),
  Variant Harmonization (per-variant), Phenotype Extraction (per-patient), HPO Linking (per-phenotype).

Step 3 — Route the request
**Critical distinction for global agents:**
- Questions ABOUT VARIANTS (why weren't they extracted, how were they processed, etc.) → "Variant Extraction"
- Questions ABOUT PATIENTS (demographics, identification, status, etc.) → "Patient Extraction"
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


def make_routing_agent(paper_id: int) -> Agent:
    fetch_tasks_for_type = _make_fetch_tasks_tool(paper_id)
    return Agent(
        name='chat_router',
        instructions=BASE_SYSTEM_INSTRUCTIONS,
        model=env.OPENAI_API_DEPLOYMENT,
        output_type=ChatRoutingOutput,
        tools=[fetch_tasks_for_type],  # type: ignore[list-item]
    )
