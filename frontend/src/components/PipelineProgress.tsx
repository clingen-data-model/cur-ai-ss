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
import type { TaskResp, TaskStatsResp } from '@/api/generated/types.gen'

function TrackBar({ track }: { track: TrackProgress }) {
  return (
    <Progress
      value={track.percent}
      aria-label={`${track.label} progress`}
      className="gap-x-2 gap-y-1"
      // Failed is the one state a bar's length cannot express: a stalled track
      // and a broken one are the same width. Running gets a sweep for the same
      // reason -- progress advances only when a whole task finishes, and tasks
      // take minutes, so a working bar is motionless most of the time.
      indicatorClassName={cn(
        track.failed && 'bg-destructive',
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
