/* Turning a paper's tasks into a live, per-task-type status list.
 *
 * One row per pipeline task type, in execution order, each independently
 * pending / running / complete / failed -- unlike the four aggregate bars this
 * replaces, a row's completeness is read straight off its own instances'
 * status plus its direct predecessor's, never off run-scoping or a
 * whole-paper judgement. See PREDECESSOR_TASK_TYPES (lib/tasks/models.py) for
 * why that is enough: a fan-out type's rows are always fully created by the
 * time its direct predecessor type is itself fully Completed, so nothing can
 * trickle in later once a row is marked complete.
 */
import { RERUNNABLE_TASK_TYPES } from '@/components/PaperActions'
import type {
  TaskResp,
  TaskStatsResp,
  TaskType,
} from '@/api/generated/types.gen'

export type TaskRowStatus = 'pending' | 'running' | 'complete' | 'failed'

export interface TaskRowProgress {
  type: TaskType
  trackId: string
  status: TaskRowStatus
  /** Seconds elapsed (running, live) or taken (complete, frozen). Null otherwise. */
  elapsedSeconds: number | null
  errorMessage: string | null
  /** How many rows of this type exist -- >1 for a fan-out type (per-patient, etc). */
  instanceCount: number
}

function earliestStart(tasks: TaskResp[]): number | null {
  const times = tasks
    .map((t) => t.started_at)
    .filter((s): s is string => !!s)
    .map((s) => new Date(s).getTime())
  return times.length ? Math.min(...times) : null
}

function latestUpdate(tasks: TaskResp[]): number | null {
  const times = tasks.map((t) => new Date(t.updated_at).getTime())
  return times.length ? Math.max(...times) : null
}

export function taskTypeProgress(
  tasks: TaskResp[],
  stats: TaskStatsResp | undefined,
  now: number = Date.now(),
): TaskRowProgress[] {
  const predecessorsOf = stats?.predecessor_task_types ?? {}
  const trackOfType: Record<string, string> = {}
  for (const track of stats?.tracks ?? []) {
    for (const type of track.task_types) trackOfType[type] = track.id
  }

  const completeByType: Partial<Record<TaskType, boolean>> = {}
  return RERUNNABLE_TASK_TYPES.map((type) => {
    const mine = tasks.filter((t) => t.type === type)
    const running = mine.filter((t) => t.status === 'Running')
    const failed = mine.filter((t) => t.status === 'Failed')

    const predecessorsDone = (predecessorsOf[type] ?? []).every(
      (p) => completeByType[p],
    )
    const complete =
      running.length === 0 &&
      predecessorsDone &&
      mine.length > 0 &&
      mine.every((t) => t.status === 'Completed')
    completeByType[type] = complete

    const status: TaskRowStatus =
      running.length > 0
        ? 'running'
        : complete
          ? 'complete'
          : failed.length > 0
            ? 'failed'
            : 'pending'

    const completed = mine.filter((t) => t.status === 'Completed')
    const startedAt = earliestStart(status === 'running' ? running : completed)
    let elapsedSeconds: number | null = null
    if (status === 'running' && startedAt !== null) {
      elapsedSeconds = Math.max(0, (now - startedAt) / 1000)
    } else if (status === 'complete') {
      const endedAt = latestUpdate(completed)
      elapsedSeconds =
        startedAt !== null && endedAt !== null
          ? Math.max(0, (endedAt - startedAt) / 1000)
          : null
    }

    return {
      type,
      trackId: trackOfType[type] ?? 'paper',
      status,
      elapsedSeconds,
      errorMessage: failed.find((t) => t.error_message)?.error_message ?? null,
      instanceCount: mine.length,
    }
  })
}

/** "12s" / "1m 12s" / "2h 05m" -- real per-second precision, since this ticks
 *  live rather than reading a coarse historical median. */
export function formatElapsedLive(seconds: number): string {
  const total = Math.floor(seconds)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  if (hours > 0) return `${hours}h ${String(minutes).padStart(2, '0')}m`
  if (minutes > 0) return `${minutes}m ${String(secs).padStart(2, '0')}s`
  return `${secs}s`
}
