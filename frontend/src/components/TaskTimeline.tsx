/* A paper's extraction progress, as one live row per pipeline task type,
 * grouped into the pipeline's stages (lib/tasks/tracks.py: Reading the paper,
 * Individuals and phenotypes, Variants, ...).
 *
 * Each stage is one expandable row saying whether it is done; a stage that is
 * running or has failed starts open, so what a curator needs to see is shown
 * and the finished or waiting stages stay one line each. Inside, a step goes
 * pending -> shimmering-with-a-counter while running -> checked off once
 * complete, the moment its own work lands. The grouping and completion rules
 * live in lib/taskTimeline; this file only renders them.
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { Check, ChevronRight, X, Zap } from 'lucide-react'
import { useNow } from '@/hooks/useNow'
import { formatElapsedLive, taskTypeProgress } from '@/lib/taskTimeline'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { TaskResp, TaskStatsResp } from '@/api/generated/types.gen'
import { stageProgress } from '@/lib/taskTimeline'
import type { StageProgress, TaskRowProgress, TaskRowStatus } from '@/lib/taskTimeline'
import { QUICK_RUN_LABEL } from '@/components/QuickRunCheckbox'
import { taskLabel } from '@/lib/taskLabel'

// Same palette PipelineProgress used, keyed by the track ids in
// lib/tasks/tracks.py -- one colour per track so the list reads as four
// grouped phases rather than one long undifferentiated column.
const TRACK_ACCENT: Record<string, string> = {
  paper: 'var(--color-chart-1)',
  patients: 'var(--color-chart-2)',
  variants: 'var(--color-chart-3)',
  analysis: 'var(--color-chart-4)',
  verification: 'var(--color-chart-5)',
}

function StatusMarker({
  row,
  accent,
}: {
  row: { status: TaskRowStatus; errorMessage: string | null }
  accent: string
}) {
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
        {taskLabel(row.type)}
        {row.instanceCount > 1 && (
          <span className="text-muted-foreground"> ({row.instanceCount})</span>
        )}
      </span>

      {/* A quick run looks like any other row once it is done; the marker is
        * how a curator tells a result they should read with that in mind. */}
      {row.quick && (
        <Tooltip>
          <TooltipTrigger render={<span className="flex shrink-0 cursor-help" />}>
            <Zap className="size-3 text-muted-foreground" />
          </TooltipTrigger>
          <TooltipContent>{QUICK_RUN_LABEL}</TooltipContent>
        </Tooltip>
      )}

      {row.elapsedSeconds !== null && (
        <span className="ml-auto shrink-0 text-xs tabular-nums text-muted-foreground">
          {formatElapsedLive(row.elapsedSeconds)}
        </span>
      )}
    </div>
  )
}

const STAGE_STATUS_TEXT: Record<TaskRowStatus, string> = {
  complete: 'Done',
  running: 'In progress',
  failed: 'Needs attention',
  pending: 'Waiting',
}

function StageRow({
  stage,
  open,
  onToggle,
}: {
  stage: StageProgress
  open: boolean
  onToggle: () => void
}) {
  const accent = TRACK_ACCENT[stage.id] ?? 'var(--color-primary)'
  // Collapsed and under way: name the step it is on, so the one line still
  // says what is happening.
  const current = stage.rows.find((row) => row.status === 'running')
  const failedRow = stage.rows.find((row) => row.status === 'failed')
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center gap-2.5 rounded py-1 text-left text-sm hover:bg-muted/50"
        style={{ '--shimmer-text-tint': accent } as CSSProperties}
      >
        <span className="flex size-4 shrink-0 items-center justify-center">
          <StatusMarker
            row={{ status: stage.status, errorMessage: failedRow?.errorMessage ?? null }}
            accent={accent}
          />
        </span>
        <span
          className={cn(
            'truncate font-medium',
            stage.status === 'pending' && 'text-muted-foreground',
          )}
        >
          {stage.label}
        </span>
        <span className="ml-auto flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
          {!open && current ? (
            <span className="max-w-40 truncate">{taskLabel(current.type)}…</span>
          ) : (
            STAGE_STATUS_TEXT[stage.status]
          )}
          <ChevronRight className={cn('size-3.5 transition-transform', open && 'rotate-90')} />
        </span>
      </button>
      {open && (
        <div className="ml-2 border-l pl-3.5">
          {stage.rows.map((row) => (
            <TaskRow key={row.type} row={row} />
          ))}
        </div>
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
  const stages = stageProgress(rows, stats)
  // A stage the curator opened or closed stays that way; the rest follow
  // their status (open while running or failed).
  const [toggled, setToggled] = useState<Record<string, boolean>>({})

  return (
    <div className={cn('max-h-80 space-y-0.5 overflow-y-auto', className)}>
      {stages
        ? stages.map((stage) => {
            const open =
              toggled[stage.id] ?? (stage.status === 'running' || stage.status === 'failed')
            return (
              <StageRow
                key={stage.id}
                stage={stage}
                open={open}
                onToggle={() => setToggled((prev) => ({ ...prev, [stage.id]: !open }))}
              />
            )
          })
        : rows.map((row) => <TaskRow key={row.type} row={row} />)}
    </div>
  )
}
