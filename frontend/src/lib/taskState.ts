/* Whether the agent that populates a section has actually run.
 *
 * A paper's page is reachable at any point in the pipeline, so every section
 * can be asked to render data that does not exist yet. Empty therefore has two
 * meanings -- "the agent has not run" and "the agent ran and found nothing" --
 * and only the task rows can tell them apart. Without that distinction the
 * Unassociated tabs claimed "every extracted patient is linked to a variant"
 * before linking had run, when in fact none was.
 *
 * The rule every caller applies: empty means "none" only when the producing
 * task is `complete`. Anything else means "not yet".
 *
 * This is the Streamlit gate (is_task_completed, lib/tasks/misc.py) with its
 * two limits removed -- see taskState below.
 */
import { TaskStatus, TaskType } from '@/api/generated/types.gen'
import type { TaskResp } from '@/api/generated/types.gen'

export type TaskState = 'not-started' | 'waiting' | 'running' | 'failed' | 'complete'

/** Which row a scoped task belongs to. Several task types run once per patient
 * (Phenotype Extraction, HPO Linking, Patient Demographics) or per family (the
 * Segregation pair), so a paper holds many rows of the same type and a single
 * per-row panel must ask about its own. */
export interface TaskScope {
  patientId?: number
  variantId?: number
  familyId?: number
  phenotypeId?: number
}

function inScope(task: TaskResp, scope: TaskScope): boolean {
  if (scope.patientId !== undefined && task.patient_id !== scope.patientId) return false
  if (scope.variantId !== undefined && task.variant_id !== scope.variantId) return false
  if (scope.familyId !== undefined && task.family_id !== scope.familyId) return false
  if (scope.phenotypeId !== undefined && task.phenotype_id !== scope.phenotypeId)
    return false
  return true
}

/* Deliberately not a port of is_task_completed, which returns on the *first*
 * task matching a type and so answers for an arbitrary patient when asked about
 * a per-patient type. It also collapses "never queued" into the same false as
 * "queued and waiting", which is the distinction a reader needs to know whether
 * anything is coming.
 *
 * Unscoped and several rows match, the worst state wins, except that `complete`
 * requires all of them -- a phenotype column is only trustworthy once every
 * patient's linking has landed.
 */
export function taskState(
  tasks: TaskResp[],
  type: TaskType,
  scope: TaskScope = {},
): TaskState {
  const matching = tasks.filter((t) => t.type === type && inScope(t, scope))
  if (matching.length === 0) return 'not-started'
  if (matching.some((t) => t.status === TaskStatus.FAILED)) return 'failed'
  if (matching.some((t) => t.status === TaskStatus.RUNNING)) return 'running'
  if (
    matching.some(
      (t) => t.status === TaskStatus.PENDING || t.status === TaskStatus.QUEUED,
    )
  )
    return 'waiting'
  return 'complete'
}

/** Sections render their own content only once this is true; until then an
 * empty table would be an assertion the data does not support. */
export function isTaskComplete(
  tasks: TaskResp[],
  type: TaskType,
  scope: TaskScope = {},
): boolean {
  return taskState(tasks, type, scope) === 'complete'
}

/* TaskType values are already display strings ('HPO Linking'), but they name
 * the agent rather than the thing a curator is looking at, so a section can
 * pass a label that reads naturally in these sentences. */
export function taskStateMessage(
  state: TaskState,
  type: TaskType,
  label: string = type,
): { title: string; description: string } {
  switch (state) {
    case 'not-started':
      return {
        title: `${label} hasn't run yet`,
        description: `This paper has no ${type} task. Queue one from Rerun Agents to populate this section.`,
      }
    case 'waiting':
      return {
        title: `${label} hasn't run yet`,
        description: `${type} is queued behind earlier steps. This section fills in once it completes.`,
      }
    case 'running':
      return {
        title: `${label} is running`,
        description: `${type} is in progress. This section fills in once it completes.`,
      }
    case 'failed':
      return {
        title: `${label} failed`,
        description: `${type} did not complete, so this section has no data. Re-run it from Rerun Agents to try again.`,
      }
    case 'complete':
      return { title: '', description: '' }
  }
}
