/* A paper's extraction progress, as one live row per pipeline task type.
 *
 * Replaces the four aggregate progress bars (see git history for
 * PipelineProgress/lib/pipeline): pending -> shimmering-with-a-counter while
 * running -> checked off once complete, one row per type rather than one bar
 * per track, so a row goes green the moment its own work lands instead of
 * waiting on the whole pipeline. The grouping and completion rule live in
 * lib/taskTimeline; this file only renders them.
 */
import type { CSSProperties } from 'react'
import { Check, X } from 'lucide-react'
import { useNow } from '@/hooks/useNow'
import { formatElapsedLive, taskTypeProgress } from '@/lib/taskTimeline'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { TaskResp, TaskStatsResp } from '@/api/generated/types.gen'
import type { TaskRowProgress } from '@/lib/taskTimeline'

// Same palette PipelineProgress used, keyed by the track ids in
// lib/tasks/tracks.py -- one colour per track so the list reads as four
// grouped phases rather than one long undifferentiated column.
const TRACK_ACCENT: Record<string, string> = {
  paper: 'var(--color-chart-1)',
  patients: 'var(--color-chart-2)',
  variants: 'var(--color-chart-3)',
  analysis: 'var(--color-chart-4)',
}

function StatusMarker({ row, accent }: { row: TaskRowProgress; accent: string }) {
  if (row.status === 'complete') {
    return <Check className="size-3.5" style={{ color: accent }} />
  }
  if (row.status === 'failed') {
    const icon = <X className="size-3.5 text-destructive" />
    if (!row.errorMessage) return icon
    return (
      <Tooltip>
        <TooltipTrigger render={<span className="cursor-help" />}>{icon}</TooltipTrigger>
        <TooltipContent className="max-w-72">{row.errorMessage}</TooltipContent>
      </Tooltip>
    )
  }
  if (row.status === 'running') {
    return (
      <span
        className="size-2 rounded-full animate-pulse"
        style={{ backgroundColor: accent }}
      />
    )
  }
  return <span className="size-1.5 rounded-full bg-muted-foreground/30" />
}

function TaskRow({ row }: { row: TaskRowProgress }) {
  const accent = TRACK_ACCENT[row.trackId] ?? 'var(--color-primary)'

  return (
    <div
      className="flex items-center gap-2.5 py-1 text-sm"
      style={{ '--shimmer-text-tint': accent } as CSSProperties}
    >
      <span className="flex size-4 shrink-0 items-center justify-center">
        <StatusMarker row={row} accent={accent} />
      </span>

      <span
        className={cn(
          'truncate',
          row.status === 'pending' && 'text-muted-foreground',
          row.status === 'complete' && 'text-foreground',
          row.status === 'running' && 'shimmer-text',
        )}
      >
        {row.type}
        {row.instanceCount > 1 && (
          <span className="text-muted-foreground"> ({row.instanceCount})</span>
        )}
      </span>

      {row.elapsedSeconds !== null && (
        <span className="ml-auto shrink-0 text-xs tabular-nums text-muted-foreground">
          {formatElapsedLive(row.elapsedSeconds)}
        </span>
      )}
    </div>
  )
}

export function TaskTimeline({
  tasks,
  stats,
  className,
}: {
  tasks: TaskResp[]
  stats?: TaskStatsResp
  className?: string
}) {
  const anyRunning = tasks.some((t) => t.status === 'Running')
  const now = useNow(anyRunning)
  const rows = taskTypeProgress(tasks, stats, now)

  return (
    <div className={cn('max-h-80 space-y-0.5 overflow-y-auto', className)}>
      {rows.map((row) => (
        <TaskRow key={row.type} row={row} />
      ))}
    </div>
  )
}
