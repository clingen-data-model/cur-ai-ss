/* A paper's extraction progress, as one bar per pipeline track.
 *
 * Four bars rather than one because the pipeline forks after Paper Classifier
 * and the branches run concurrently -- see lib/pipeline for the cut. The
 * grouping and arithmetic live there; this file only renders them.
 */
import { Progress, ProgressLabel, ProgressValue } from '@/components/ui/progress'
import {
  formatDuration,
  remainingSeconds,
  trackProgress,
  type TrackProgress,
} from '@/lib/pipeline'
import { cn } from '@/lib/utils'
import type { CSSProperties } from 'react'
import type { TaskResp, TaskStatsResp } from '@/api/generated/types.gen'

/* A colour per track, so four bars stacked together read as four different
 * things rather than one measurement in four pieces.
 *
 * The chart tokens rather than hand-picked hues: they are the theme's
 * categorical palette, already defined for both light and dark, and they carry
 * no status meaning that would collide with the one colour here that does --
 * destructive, for a failed track.
 *
 * Keyed by the track ids in lib/tasks/tracks.py. An id with no entry falls back
 * to the primary accent rather than disappearing.
 */
const TRACK_ACCENT: Record<string, string> = {
  paper: 'var(--color-chart-1)',
  patients: 'var(--color-chart-2)',
  variants: 'var(--color-chart-3)',
  analysis: 'var(--color-chart-4)',
}

function TrackBar({ track }: { track: TrackProgress }) {
  // Read by the fill, and by the sweep an indeterminate track draws across
  // itself -- so a waiting track shimmers in its own colour instead of
  // borrowing the primary accent from a track it is not.
  const accent =
    (track.failed
      ? 'var(--color-destructive)'
      : TRACK_ACCENT[track.id]) ?? 'var(--color-primary)'

  return (
    <Progress
      value={track.percent}
      aria-label={`${track.label} progress`}
      className="gap-x-2 gap-y-1"
      style={{ '--track-accent': accent } as CSSProperties}
      // Failed is the one state a bar's length cannot express: a stalled track
      // and a broken one are the same width, so it overrides the track's own
      // colour above. Running gets a sweep for the same reason -- progress
      // advances only when a whole task finishes, and tasks take minutes, so a
      // working bar is motionless most of the time.
      indicatorClassName={cn(
        'bg-[var(--track-accent)]',
        track.running && !track.failed && 'shimmer',
      )}
    >
      <ProgressLabel className="text-xs font-normal">{track.label}</ProgressLabel>
      <ProgressValue
        className="text-xs"
        render={
          <span>
            {/* Counts, not the percentage the bar is drawn from. The bar is
                weighted by expected duration, so showing that number here would
                contradict "2 of 8" sitting beside it. */}
            {track.total === 0 ? '—' : `${track.done}/${track.total}`}
          </span>
        }
      />
    </Progress>
  )
}

export function PipelineProgress({
  tasks,
  stats,
  className,
}: {
  tasks: TaskResp[]
  stats?: TaskStatsResp
  className?: string
}) {
  const tracks = trackProgress(tasks, stats)
  const remaining = remainingSeconds(tracks)
  const anyRunning = tracks.some((t) => t.running)

  return (
    <div className={cn('space-y-2.5', className)}>
      {tracks.map((track) => (
        <TrackBar key={track.id} track={track} />
      ))}
      {/* Only while something is actually moving: a finished paper does not
          need "0 min left", and a queued one has no honest estimate. */}
      {anyRunning && remaining !== null && (
        <p className="text-xs text-muted-foreground pt-0.5">
          About {formatDuration(remaining)} left
        </p>
      )}
    </div>
  )
}
