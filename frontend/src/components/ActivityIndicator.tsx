/* Header indicator for papers currently extracting.
 *
 * Answers "is anything still going?" from wherever you happen to be -- the
 * per-paper bars only answer it if you already know which paper to look at.
 *
 * Renders nothing when nothing is running, which is nearly always. A permanent
 * "0 extracting" would be noise occupying the header for the state it spends
 * almost all its time in.
 */
import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { ChevronDown, Loader2, RefreshCw, X } from 'lucide-react'
import {
  getTaskStatsStatsGet,
  listActivePapersPapersActiveGet,
  listTasksPapersPaperIdTasksGet,
} from '@/api/generated'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { TaskTimeline } from '@/components/TaskTimeline'
import { RerunTaskDialog } from '@/components/PaperActions'
import { Hint } from '@/components/Hint'
import type { ActivePaperResp, TaskStatsResp } from '@/api/generated/types.gen'
import { POLL_WHILE_ACTIVE_MS } from '@/lib/polling'
import { paperProgress } from '@/lib/taskTimeline'
import { taskLabel } from '@/lib/taskLabel'
import { cn } from '@/lib/utils'

// Polled, so the cadence is a real cost decision (lib/polling.ts); while
// nothing is running there is nothing to be timely about.
const POLL_WHILE_IDLE_MS = 60_000

// A full timeline is some 18 rows; two of them already fill a laptop screen.
// So one paper shows its timeline, as it always has, and from two up every
// paper is one collapsed row that a click opens, one at a time. The list
// itself stops at MAX_LISTED: past that the papers table is the better view.
const MAX_LISTED = 10

/** A paper's task list as the full timeline. Mounted only for a row that is
 *  showing it, so a collapsed row costs no request: the tasks are polled per
 *  paper, and a bulk re-queue puts dozens of papers in the list at once. */
function PaperTimeline({ paperId, stats }: { paperId: number; stats?: TaskStatsResp }) {
  const { data } = useQuery({
    queryKey: ['paper-tasks', paperId],
    queryFn: () =>
      listTasksPapersPaperIdTasksGet({
        path: { paper_id: paperId },
        throwOnError: true,
      }),
    refetchInterval: POLL_WHILE_ACTIVE_MS,
  })
  return <TaskTimeline tasks={data ?? []} stats={stats} />
}

/** The collapsed row's second line: the step the paper is on and how far
 *  along it is, from the counts GET /papers/active already carries. */
function ProgressSummary({
  paper,
  open,
  onToggle,
}: {
  paper: ActivePaperResp
  open: boolean
  onToggle: () => void
}) {
  const progress = paperProgress(paper.task_counts ?? [])
  const [current, ...others] = progress.running
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className="flex w-full items-center gap-2 rounded py-0.5 text-xs text-muted-foreground hover:text-foreground cursor-pointer transition-colors"
    >
      <span className="flex size-4 shrink-0 items-center justify-center">
        {current ? (
          <span className="size-2 rounded-full bg-primary animate-pulse" />
        ) : (
          <span className="size-1.5 rounded-full bg-muted-foreground/30" />
        )}
      </span>
      <span className="truncate">
        {current ? taskLabel(current) : 'Waiting to start'}
        {others.length > 0 && ` +${others.length}`}
      </span>
      {progress.failed && (
        <span className="flex shrink-0 items-center gap-0.5 text-destructive">
          <X className="size-3" aria-hidden />
          failed step
        </span>
      )}
      <span className="ml-auto shrink-0 tabular-nums">
        {progress.done} of {progress.total}
      </span>
      <ChevronDown
        className={cn('size-3.5 shrink-0 transition-transform', open && 'rotate-180')}
        aria-hidden
      />
    </button>
  )
}

function PaperRow({
  paper,
  stats,
  collapsible,
  open,
  onToggle,
}: {
  paper: ActivePaperResp
  stats?: TaskStatsResp
  /** False while this is the only paper: its timeline is simply shown. */
  collapsible: boolean
  open: boolean
  onToggle: () => void
}) {
  const [rerunOpen, setRerunOpen] = useState(false)

  return (
    <div className="shrink-0 space-y-1 py-1.5">
      <div className="flex items-center gap-1.5">
        <Link
          to="/papers/$paperId/extraction"
          params={{ paperId: String(paper.id) }}
          className="block flex-1 truncate text-sm font-medium hover:underline underline-offset-4"
        >
          {paper.title ?? paper.filename}
        </Link>
        <Hint label="Re-run agents">
          <button
            type="button"
            onClick={() => setRerunOpen(true)}
            className="flex items-center justify-center size-6 shrink-0 rounded text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer transition-colors"
          >
            <RefreshCw className="size-3.5" />
          </button>
        </Hint>
      </div>
      {collapsible && <ProgressSummary paper={paper} open={open} onToggle={onToggle} />}
      {(!collapsible || open) && <PaperTimeline paperId={paper.id} stats={stats} />}
      <RerunTaskDialog paper={paper} open={rerunOpen} onOpenChange={setRerunOpen} />
    </div>
  )
}

export function ActivityIndicator() {
  const queryClient = useQueryClient()
  const { data } = useQuery({
    queryKey: ['papers', 'active'],
    queryFn: () => listActivePapersPapersActiveGet(),
    // Slow while idle, brisk while something runs. A fixed fast interval would
    // be a permanent request stream for a state that is almost always empty.
    refetchInterval: (query) =>
      query.state.data?.length ? POLL_WHILE_ACTIVE_MS : POLL_WHILE_IDLE_MS,
  })

  // By id, so a row keeps its place while the tasks under it come and go.
  const papers = [...(data ?? [])].sort((a, b) => a.id - b.id)
  const listed = papers.slice(0, MAX_LISTED)
  const unlisted = papers.length - listed.length
  const [openPaperId, setOpenPaperId] = useState<number | null>(null)

  // This is the one polled endpoint (see list_active_papers), and its answer
  // carries the signal every other view needs: which papers are in flight,
  // and per paper when a task last changed state. Nothing else polls.
  //
  // A paper entering or leaving the set is when the table's status badges
  // change, so the papers lists are refreshed then, once. A paper's stamp
  // moving is a task of it finishing (or starting), so every query keyed on
  // that paper -- its page's own paper, patients, variants, occurrences,
  // flags -- is refreshed then, and a section on "fills in once it completes"
  // fills in. A paper leaving the set counts as a change too, for the last
  // task.
  const stamps = papers.map((p) => `${p.id}:${p.tasks_changed_at ?? ''}`).sort().join(',')
  const previousStamps = useRef(stamps)
  useEffect(() => {
    if (stamps === previousStamps.current) return
    const parse = (s: string) =>
      new Map(s.split(',').filter(Boolean).map((e) => [Number(e.split(':')[0]), e]))
    const before = parse(previousStamps.current)
    const after = parse(stamps)
    previousStamps.current = stamps
    const changed = new Set(
      [...before.keys(), ...after.keys()].filter((id) => before.get(id) !== after.get(id)),
    )
    const setChanged = [...changed].some((id) => before.has(id) !== after.has(id))
    queryClient.invalidateQueries({
      predicate: (query) =>
        (setChanged && query.queryKey[0] === 'papers' && query.queryKey[1] !== 'active') ||
        (typeof query.queryKey[1] === 'number' && changed.has(query.queryKey[1])),
    })
  }, [stamps, queryClient])

  // Shared with the card popovers, and only fetched once something is running.
  const { data: stats } = useQuery({
    queryKey: ['task-stats'],
    queryFn: () => getTaskStatsStatsGet(),
    enabled: papers.length > 0,
    staleTime: 30 * 60 * 1000,
  })

  if (papers.length === 0) return null

  return (
    <Popover>
      <PopoverTrigger
        type="button"
        className="flex items-center gap-1.5 rounded px-2 py-1 text-sm text-white/90 hover:bg-white/10 cursor-pointer transition-colors"
      >
        <Loader2 className="size-3.5 animate-spin" aria-hidden />
        {papers.length} extracting
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="max-h-[calc(100vh-4rem)] w-96 divide-y overflow-y-auto"
      >
        {listed.map((paper) => (
          <PaperRow
            key={paper.id}
            paper={paper}
            stats={stats}
            collapsible={papers.length > 1}
            open={paper.id === openPaperId}
            onToggle={() => setOpenPaperId(paper.id === openPaperId ? null : paper.id)}
          />
        ))}
        {/* Worth having only because the target actually answers the question:
            the papers table filtered to what is running, rather than the whole
            table with the running ones somewhere in it. */}
        <Link
          to="/"
          search={{ tab: 'papers', status: 'in-progress' }}
          className="block shrink-0 pt-2 text-sm text-muted-foreground hover:text-foreground hover:underline underline-offset-4"
        >
          {unlisted > 0
            ? `${unlisted} more in the papers table`
            : 'See all in the papers table'}
        </Link>
      </PopoverContent>
    </Popover>
  )
}
