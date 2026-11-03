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
import { Loader2, RefreshCw } from 'lucide-react'
import {
  getTaskStatsStatsGet,
  listActivePapersPapersActiveGet,
  listTasksPapersPaperIdTasksGet,
} from '@/api/generated'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { TaskTimeline } from '@/components/TaskTimeline'
import { RerunTaskDialog } from '@/components/PaperActions'
import type { PaperSummaryResp, TaskStatsResp } from '@/api/generated/types.gen'
import { POLL_WHILE_ACTIVE_MS } from '@/lib/polling'

// Polled, so the cadence is a real cost decision (lib/polling.ts); while
// nothing is running there is nothing to be timely about.
const POLL_WHILE_IDLE_MS = 60_000

function PaperRow({ paper, stats }: { paper: PaperSummaryResp; stats?: TaskStatsResp }) {
  const [rerunOpen, setRerunOpen] = useState(false)
  const { data } = useQuery({
    queryKey: ['paper-tasks', paper.id],
    queryFn: () =>
      listTasksPapersPaperIdTasksGet({
        path: { paper_id: paper.id },
        throwOnError: true,
      }),
    refetchInterval: POLL_WHILE_ACTIVE_MS,
  })

  return (
    <div className="space-y-1.5 py-1.5">
      <div className="flex items-center gap-1.5">
        <Link
          to="/papers/$paperId/extraction"
          params={{ paperId: String(paper.id) }}
          className="block flex-1 truncate text-sm font-medium hover:underline underline-offset-4"
        >
          {paper.title ?? paper.filename}
        </Link>
        <button
          type="button"
          title="Re-run agents"
          onClick={() => setRerunOpen(true)}
          className="flex items-center justify-center size-6 shrink-0 rounded text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer transition-colors"
        >
          <RefreshCw className="size-3.5" />
        </button>
      </div>
      <TaskTimeline tasks={data ?? []} stats={stats} />
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

  const papers = data ?? []

  // The table's status badges come from GET /papers, which is deliberately
  // not polled (this is the one polled endpoint; see list_active_papers).
  // Their value changes exactly when a paper enters or leaves the active set,
  // so refresh the lists then, once, rather than on a timer; and the queries
  // of each paper that entered or left, so an open paper page learns that
  // its pipeline started (someone else queued it) or finished.
  const activeIds = papers.map((p) => p.id).sort((a, b) => a - b).join(',')
  const previousIds = useRef(activeIds)
  useEffect(() => {
    if (activeIds === previousIds.current) return
    const before = new Set(previousIds.current.split(',').filter(Boolean).map(Number))
    const after = new Set(activeIds.split(',').filter(Boolean).map(Number))
    const changed = new Set([...before, ...after].filter((id) => before.has(id) !== after.has(id)))
    previousIds.current = activeIds
    queryClient.invalidateQueries({
      predicate: (query) =>
        (query.queryKey[0] === 'papers' && query.queryKey[1] !== 'active') ||
        (typeof query.queryKey[1] === 'number' && changed.has(query.queryKey[1])),
    })
  }, [activeIds, queryClient])

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
      <PopoverContent align="end" className="w-96 divide-y">
        {papers.map((paper) => (
          <PaperRow key={paper.id} paper={paper} stats={stats} />
        ))}
        {/* Worth having only because the target actually answers the question:
            the papers table filtered to what is running, rather than the whole
            table with the running ones somewhere in it. */}
        <Link
          to="/"
          search={{ tab: 'papers', status: 'in-progress' }}
          className="block pt-2 text-sm text-muted-foreground hover:text-foreground hover:underline underline-offset-4"
        >
          See all in the papers table
        </Link>
      </PopoverContent>
    </Popover>
  )
}
