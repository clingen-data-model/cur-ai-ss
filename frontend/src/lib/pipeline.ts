/* Turning a paper's tasks into the four progress bars.
 *
 * The bars measure elapsed time against a historical wall-clock budget, not
 * finished tasks against total tasks. That is what stops them running
 * backwards: a count-based denominator moves, because downstream rows do not
 * exist until their predecessor completes -- a re-run deletes the whole
 * subtree, and patient extraction discovering twelve patients enqueues twelve
 * phenotype tasks. Both make "done/total" jump back.
 *
 * Elapsed over expected cannot: the denominator is a constant from history and
 * the numerator only increases. The task counts are still shown as text, where
 * they are a factual statement rather than a progress claim.
 *
 * The grouping comes from /stats rather than being declared here, so there is
 * one definition of which task type belongs to which track. See
 * lib/tasks/tracks.py.
 */
import type {
  TaskResp,
  TaskStatsResp,
  TrackDurationStat,
} from '@/api/generated/types.gen'

export interface TrackProgress {
  id: string
  label: string
  done: number
  total: number
  /** 0-100, or null when there is nothing honest to show. */
  percent: number | null
  /** Expected seconds left, or null without a budget to subtract from. */
  remainingSeconds: number | null
  running: boolean
  failed: boolean
  complete: boolean
}

const DONE = 'Completed'
// Running, and not Queued. Queued means the scheduler has claimed the task; no
// handler is executing it, so it waits alongside Pending. `running` drives the
// shimmer and the "about N left" estimate, and neither is honest yet.
const RUNNING = 'Running'

/** Whether the pipeline has nothing outstanding anywhere.
 *
 * Judged across the whole paper, never per track. A track whose current tasks
 * have all landed is not finished -- downstream rows do not exist until their
 * predecessor completes, so Patients reads "1 of 1 done" the moment Pedigree
 * lands and then grows to 15. Snapping that to 100% and recomputing when the
 * next task appeared was exactly the backwards jump this file exists to
 * prevent.
 */
function pipelineComplete(tasks: TaskResp[], terminalTypes: string[]): boolean {
  if (tasks.length === 0 || terminalTypes.length === 0) return false
  if (tasks.some((t) => t.status !== DONE)) return false
  // Every leaf of the DAG has landed. Without this check, a paper one task into
  // its run also has "every task Completed" and would read as finished.
  return terminalTypes.every((type) =>
    tasks.some((t) => t.type === type && t.status === DONE),
  )
}

function earliestStart(tasks: TaskResp[]): number | null {
  const times = tasks
    .map((t) => t.started_at)
    .filter((s): s is string => !!s)
    .map((s) => new Date(s).getTime())
  return times.length ? Math.min(...times) : null
}

export function trackProgress(
  tasks: TaskResp[],
  stats: TaskStatsResp | undefined,
  now: number = Date.now(),
): TrackProgress[] {
  const tracks: TrackDurationStat[] = stats?.tracks ?? []
  // One judgement for the whole paper, applied to every track.
  const finished = pipelineComplete(tasks, stats?.terminal_task_types ?? [])

  return tracks.map((track) => {
    const mine = tasks.filter((t) => track.task_types.includes(t.type))
    const done = mine.filter((t) => t.status === DONE).length
    const complete = finished && mine.length > 0
    const budget = track.median_seconds

    const startedAt = earliestStart(mine)
    const elapsed = startedAt === null ? null : (now - startedAt) / 1000

    let percent: number | null = null
    let remainingSeconds: number | null = null

    if (complete) {
      // Snap rather than computing: the work is done whatever the clock says.
      percent = 100
      remainingSeconds = 0
    } else if (startedAt === null) {
      // Not started. Deliberately null rather than 0 -- the track renders
      // indeterminate, which reads as "waiting" where an empty bar reads as
      // stalled. Analysis sits here legitimately until its inputs finish.
      percent = null
    } else if (budget && budget > 0 && elapsed !== null) {
      // Capped below 100 while work remains, so the bar never claims to be
      // finished before it is. A track over its budget parks just short, which
      // is the honest reading of "longer than usual".
      // Capped just short of finished. Past the budget there is no honest
      // estimate left -- history says it should be done and it is not -- so the
      // bar parks at 99% and the countdown goes away rather than claiming
      // "0 min left" forever.
      percent = Math.min(99, Math.round((elapsed / budget) * 100))
      remainingSeconds = elapsed < budget ? Math.round(budget - elapsed) : null
    } else {
      // Running with no budget -- a track never measured here. Indeterminate
      // beats inventing a fraction.
      percent = null
    }

    return {
      id: track.id,
      label: track.label,
      done,
      total: mine.length,
      percent,
      remainingSeconds,
      running: mine.some((t) => t.status === RUNNING),
      failed: mine.some((t) => t.status === 'Failed'),
      complete,
    }
  })
}

/** Expected seconds until the whole pipeline finishes.
 *
 * The longest remaining track, not their sum: they run concurrently, and adding
 * them would roughly quadruple the estimate.
 */
export function remainingSeconds(tracks: TrackProgress[]): number | null {
  const known = tracks
    .filter((t) => !t.complete)
    .map((t) => t.remainingSeconds)
    .filter((s): s is number => s !== null)
  return known.length ? Math.max(...known) : null
}

/** "4 min", "2 h 10 min", "<1 min" -- coarse on purpose, because a median over
 *  a handful of papers does not justify second-level precision. */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return '<1 min'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest ? `${hours} h ${rest} min` : `${hours} h`
}
