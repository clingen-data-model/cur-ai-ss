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
  /** Pipeline ordering from /stats; tracks sharing a stage overlap in time. */
  stage: number
  done: number
  total: number
  /** 0-100, or null when there is nothing honest to show. */
  percent: number | null
  /** Seconds since this track's earliest task started, or null before that. */
  elapsedSeconds: number | null
  /** What history says this track takes, or null if it has never been measured. */
  budgetSeconds: number | null
  /** Expected seconds left, or null when there is no honest estimate. */
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
    // Floored at zero. Elapsed should never be negative, but it was for months:
    // the API sent timestamps with no timezone and the browser read them as
    // local, putting every start time hours in the future. That is fixed at the
    // source (lib/models/datetimes.py); this keeps a clock-skewed machine from
    // reviving the same symptom -- an empty bar and an absurd estimate.
    const elapsed = startedAt === null ? null : Math.max(0, (now - startedAt) / 1000)

    let percent: number | null
    let remainingSeconds: number | null = null

    if (complete) {
      // Snap rather than computing: the work is done whatever the clock says.
      percent = 100
      remainingSeconds = 0
    } else if (startedAt === null) {
      // Not started. percent is deliberately null rather than 0 -- the track
      // renders indeterminate, which reads as "waiting" where an empty bar
      // reads as stalled. Analysis sits here legitimately until its inputs
      // finish. It still owes its whole budget, though, which is what makes it
      // count toward the estimate instead of being invisible to it.
      percent = null
      remainingSeconds = budget && budget > 0 ? budget : null
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
      stage: track.stage,
      done,
      total: mine.length,
      percent,
      elapsedSeconds: elapsed,
      budgetSeconds: budget ?? null,
      remainingSeconds,
      running: mine.some((t) => t.status === RUNNING),
      failed: mine.some((t) => t.status === 'Failed'),
      complete,
    }
  })
}

/** Expected seconds until the whole pipeline finishes.
 *
 * Stages in sequence, tracks within a stage in parallel:
 *
 *     Paper -> { Patients || Variants } -> Analysis
 *
 * so the total adds one term per stage and takes the longest track inside each.
 * Both simpler answers are wrong in a way you can watch happen. The longest
 * track overall ignores that three stages queue behind one another, and read
 * "8 min left" on a paper whose parse had not finished. The sum of all four
 * double-counts the fork, since Patients and Variants genuinely run at once.
 *
 * The stage numbers come from /stats, so this cannot drift from the DAG the
 * worker actually follows -- see lib/tasks/tracks.py.
 *
 * Null if any outstanding track has no honest estimate: one unmeasured or
 * over-budget track makes the total a guess, and a guess presented to the
 * minute is worse than no number.
 */
export function remainingSeconds(tracks: TrackProgress[]): number | null {
  const outstanding = tracks.filter((t) => !t.complete)
  if (outstanding.length === 0) return null

  const byStage = new Map<number, (number | null)[]>()
  for (const track of outstanding) {
    const stage = byStage.get(track.stage) ?? []
    stage.push(track.remainingSeconds)
    byStage.set(track.stage, stage)
  }

  let total = 0
  for (const remaining of byStage.values()) {
    if (remaining.some((s) => s === null)) return null
    total += Math.max(...(remaining as number[]))
  }
  return total
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
