/* Grouping a paper's tasks into the four tracks the progress bars show.
 *
 * The pipeline is a DAG, not a chain: after Paper Classifier it forks into
 * three branches that run concurrently and rejoin at Patient Variant
 * Occurrences. Four parallel bars represent that honestly; a single segmented
 * bar would imply an order that does not exist.
 *
 * The cut is by subject rather than by phase because it matches the entities
 * the rest of the UI already talks about, and because two of the tracks fan out
 * per patient and per variant -- a paper has ~17 task types but ~96 tasks, so
 * "Patients 7/12" is information a single aggregate bar would destroy.
 */
import type { TaskResp, TaskStatsResp, TaskType } from '@/api/generated/types.gen'

export type TrackId = 'paper' | 'patients' | 'variants' | 'analysis'

export const TRACKS: { id: TrackId; label: string; types: TaskType[] }[] = [
  {
    id: 'paper',
    label: 'Paper',
    types: ['PDF Parsing', 'Paper Classifier', 'Paper Metadata'],
  },
  {
    id: 'patients',
    label: 'Patients',
    types: [
      'Pedigree Description',
      'Patient Extraction',
      'Patient Demographics',
      'Phenotype Extraction',
      'HPO Linking',
    ],
  },
  {
    id: 'variants',
    label: 'Variants',
    types: ['Variant Extraction', 'Variant Harmonization', 'Variant Annotation'],
  },
  {
    id: 'analysis',
    label: 'Analysis',
    types: [
      'Patient Variant Occurrences',
      'Segregation Evidence Extraction',
      'Segregation Analysis Computed',
      'Compound Het Evaluation',
      'MONDO Linking',
    ],
  },
]

// 'General Paper Question' is deliberately in no track: it is ad-hoc chat
// created by the router, not pipeline work, and counting it would make a paper
// look unfinished every time someone asked a question about it.
const TRACK_OF = new Map<TaskType, TrackId>(
  TRACKS.flatMap((track) => track.types.map((type) => [type, track.id] as const)),
)

export interface TrackProgress {
  id: TrackId
  label: string
  done: number
  total: number
  /** 0-100, or null when there is nothing to measure yet. */
  percent: number | null
  /** Expected seconds of work left, or null without duration history. */
  remainingSeconds: number | null
  running: boolean
  failed: boolean
}

const DONE: string[] = ['Completed']
const ACTIVE: string[] = ['Running', 'Queued']

/** Seconds a task of this type is expected to take, falling back to the
 *  overall median for a type never yet observed -- treating it as free would
 *  let a bar finish and then stall. */
function expectedSeconds(type: TaskType, stats: TaskStatsResp | undefined): number | null {
  if (!stats) return null
  const match = stats.task_durations.find((d) => d.type === type)
  return match ? match.median_seconds : (stats.overall_median_seconds ?? null)
}

export function trackProgress(
  tasks: TaskResp[],
  stats?: TaskStatsResp,
): TrackProgress[] {
  return TRACKS.map((track) => {
    const mine = tasks.filter((t) => TRACK_OF.get(t.type) === track.id)
    const done = mine.filter((t) => DONE.includes(t.status)).length

    // Weighted by expected duration rather than task count. The count is not
    // stable -- patient extraction discovering twelve patients enqueues twelve
    // phenotype tasks -- so a count-based fraction jumps backwards as work is
    // discovered. Weighting by time only extends the estimate.
    let doneWeight = 0
    let totalWeight = 0
    let remaining = 0
    let weighable = mine.length > 0
    for (const task of mine) {
      const seconds = expectedSeconds(task.type, stats)
      if (seconds === null) {
        weighable = false
        continue
      }
      totalWeight += seconds
      if (DONE.includes(task.status)) doneWeight += seconds
      else remaining += seconds
    }

    return {
      id: track.id,
      label: track.label,
      done,
      total: mine.length,
      // null, not 0, when there is nothing to measure -- the honest reading of
      // "this has not started and we do not yet know how big it is", where 0%
      // reads as stuck. Base UI only marks the track data-indeterminate; the
      // styling that makes it look different from 0% is ours, in index.css.
      percent:
        mine.length === 0
          ? null
          : weighable && totalWeight > 0
            ? Math.round((doneWeight / totalWeight) * 100)
            : Math.round((done / mine.length) * 100),
      remainingSeconds: weighable && mine.length > 0 ? Math.round(remaining) : null,
      running: mine.some((t) => ACTIVE.includes(t.status)),
      failed: mine.some((t) => t.status === 'Failed'),
    }
  })
}

/** Expected seconds until the whole pipeline finishes.
 *
 * The tracks run concurrently, so this is the longest remaining track rather
 * than their sum -- adding them would roughly quadruple the estimate.
 */
export function remainingSeconds(tracks: TrackProgress[]): number | null {
  const known = tracks
    .map((t) => t.remainingSeconds)
    .filter((s): s is number => s !== null)
  return known.length ? Math.max(...known) : null
}

/** "4 min", "2 h 10 min", "<1 min" -- deliberately coarse, because the
 *  underlying medians do not justify second-level precision. */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return '<1 min'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest ? `${hours} h ${rest} min` : `${hours} h`
}
