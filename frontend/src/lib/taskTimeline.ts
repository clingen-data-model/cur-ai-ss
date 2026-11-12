/* Turning a paper's tasks into a live, per-task-type status list.
 *
 * One row per pipeline task type, in execution order, each judged only by its
 * own instances -- never by a predecessor type's status. An earlier version
 * gated a row's completeness on its direct predecessor also being complete
 * (to stop a fan-out row reading "1 of 1 done" the moment its first row
 * landed, before the rest existed). That gate broke on real data two
 * different ways: computed in the rerun dropdown's flat display order rather
 * than true DAG order, so a predecessor later in that list read as
 * permanently unfinished; and a paper old enough to predate some task types
 * entirely (zero rows, ever, for an early type) could never satisfy it,
 * permanently blanking out everything downstream. Judging each row by its own
 * instances alone sidesteps both. The one type created in more than one batch
 * from independent predecessors (MONDO_LINKING, from both Paper Metadata and
 * Individual Variant Occurrences finishing) can in principle un-check briefly
 * between batches -- accepted as a minor, rare cosmetic cost.
 */
import { RERUNNABLE_TASK_TYPES } from '@/components/PaperActions'
import type {
  TaskResp,
  TaskStatsResp,
  TaskType,
  TaskTypeCounts,
} from '@/api/generated/types.gen'

export type TaskRowStatus = 'pending' | 'running' | 'complete' | 'failed'

export interface TaskRowProgress {
  type: TaskType
  trackId: string
  status: TaskRowStatus
  /** Seconds: live elapsed since the earliest running instance started, or the
   *  average per-instance duration once every instance is Completed. Null
   *  otherwise. */
  elapsedSeconds: number | null
  errorMessage: string | null
  /** How many rows of this type exist -- >1 for a fan-out type (per-patient, etc). */
  instanceCount: number
  /** Any instance ran as a quick run (tasks.budget_model): the cheaper model. */
  quick: boolean
}

/** One task type's status from how many of its instances stand where. The
 *  one rule both the full timeline (from a paper's tasks) and the header's
 *  collapsed rows (from GET /papers/active's counts) are judged by. */
export function rowStatus({
  total,
  running = 0,
  completed = 0,
  failed = 0,
}: {
  total: number
  running?: number
  completed?: number
  failed?: number
}): TaskRowStatus {
  if (running > 0) return 'running'
  if (total > 0 && completed === total) return 'complete'
  if (failed > 0) return 'failed'
  return 'pending'
}

function earliestStart(tasks: TaskResp[]): number | null {
  const times = tasks
    .map((t) => t.started_at)
    .filter((s): s is string => !!s)
    .map((s) => new Date(s).getTime())
  return times.length ? Math.min(...times) : null
}

/** Mean of each completed task's own (updated_at - started_at), not a wall-clock
 *  span across all of them -- a fan-out type's N instances run with staggered
 *  starts, so first-to-last would measure scheduling overlap rather than how
 *  long the work itself typically takes. */
function averageDuration(tasks: TaskResp[]): number | null {
  const durations = tasks
    .filter((t): t is TaskResp & { started_at: string } => !!t.started_at)
    .map((t) => (new Date(t.updated_at).getTime() - new Date(t.started_at).getTime()) / 1000)
    .filter((s) => s >= 0)
  if (!durations.length) return null
  return durations.reduce((sum, s) => sum + s, 0) / durations.length
}

export function taskTypeProgress(
  tasks: TaskResp[],
  stats: TaskStatsResp | undefined,
  now: number = Date.now(),
): TaskRowProgress[] {
  const trackOfType: Record<string, string> = {}
  for (const track of stats?.tracks ?? []) {
    for (const type of track.task_types) trackOfType[type] = track.id
  }

  return RERUNNABLE_TASK_TYPES.map((type) => {
    const mine = tasks.filter((t) => t.type === type)
    const running = mine.filter((t) => t.status === 'Running')
    const failed = mine.filter((t) => t.status === 'Failed')
    const completed = mine.filter((t) => t.status === 'Completed')
    const status = rowStatus({
      total: mine.length,
      running: running.length,
      completed: completed.length,
      failed: failed.length,
    })

    let elapsedSeconds: number | null = null
    if (status === 'running') {
      const startedAt = earliestStart(running)
      elapsedSeconds = startedAt === null ? null : Math.max(0, (now - startedAt) / 1000)
    } else if (status === 'complete') {
      elapsedSeconds = averageDuration(completed)
    }

    return {
      type,
      trackId: trackOfType[type] ?? 'paper',
      status,
      elapsedSeconds,
      errorMessage: failed.find((t) => t.error_message)?.error_message ?? null,
      instanceCount: mine.length,
      quick: mine.some((t) => t.budget_model === true),
    }
  })
}

/** A whole paper in one line, for the header's collapsed rows: the steps
 *  running now in pipeline order, whether any step has failed, and how many
 *  of the timeline's rows are checked off. */
export interface PaperProgress {
  running: TaskType[]
  failed: boolean
  done: number
  total: number
}

export function paperProgress(counts: TaskTypeCounts[]): PaperProgress {
  const statusOf = new Map(counts.map((c) => [c.type, rowStatus(c)]))
  const withStatus = (status: TaskRowStatus) =>
    RERUNNABLE_TASK_TYPES.filter((type) => statusOf.get(type) === status)
  return {
    running: withStatus('running'),
    failed: withStatus('failed').length > 0,
    done: withStatus('complete').length,
    total: RERUNNABLE_TASK_TYPES.length,
  }
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
