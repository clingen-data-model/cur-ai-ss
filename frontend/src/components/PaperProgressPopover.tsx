/* A paper's extraction-status badge, clickable for pipeline detail.
 *
 * Shared between the gene table's cards and the all-papers table's rows, so
 * both give the same "click the badge -> four progress bars -> View pipeline
 * -> full DAG" flow rather than two independent takes on it. Lifted out of
 * GeneTable, which was its only caller until the papers table needed the same
 * click target on its own status cell.
 */
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'
import { getTaskStatsStatsGet, listTasksPapersPaperIdTasksGet } from '@/api/generated'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { TaskTimeline } from '@/components/TaskTimeline'
import { TaskDAG } from '@/components/TaskDAG'
import { RerunTaskDialog } from '@/components/PaperActions'
import type { PaperSummaryResp } from '@/api/generated/types.gen'

/** Fetches a paper's tasks on demand, so the list response need not carry them.
 *
 * GET /papers returns one summarised `status` per paper rather than its task
 * list -- embedding them measured at 90.5% of that response. The full list is
 * only needed by the DAG, which lives behind a dialog, so it is fetched when
 * that dialog opens and cached per paper thereafter.
 */
function PaperTaskDAG({ paperId, enabled }: { paperId: number; enabled: boolean }) {
  const { data, isPending, isError } = useQuery({
    queryKey: ['paper-tasks', paperId],
    queryFn: () =>
      listTasksPapersPaperIdTasksGet({ path: { paper_id: paperId }, throwOnError: true }),
    enabled,
  })

  if (isPending) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    )
  }
  if (isError) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-destructive">
        Could not load pipeline tasks.
      </div>
    )
  }
  return <TaskDAG tasks={data ?? []} />
}

/** The badge's click target: four progress bars, with the full DAG one step
 *  further in.
 *
 * A popover rather than a hover card because it holds a button, and hover cards
 * are keyboard- and touch-hostile. Its queries are disabled until it opens, so
 * a table or grid of papers does not fetch tasks for every row on screen.
 */
export function PaperProgressPopover({
  paper,
  children,
}: {
  paper: PaperSummaryResp
  children: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const [dagOpen, setDagOpen] = useState(false)
  const [rerunOpen, setRerunOpen] = useState(false)
  const isRunning = paper.status === 'running'

  const tasksQuery = useQuery({
    queryKey: ['paper-tasks', paper.id],
    queryFn: () =>
      listTasksPapersPaperIdTasksGet({
        path: { paper_id: paper.id },
        throwOnError: true,
      }),
    enabled: open,
    // Matches ActivityIndicator's polling: the worker only claims new work
    // every 10s, so anything faster shows the same rows twice. Off entirely
    // once nothing is in flight -- a finished paper's popover has nothing left
    // to learn by polling.
    refetchInterval: (query) =>
      query.state.data?.some((t) => t.status === 'Running' || t.status === 'Queued')
        ? 5_000
        : false,
  })

  // Shared across every badge on screen: one response backs all of them.
  const statsQuery = useQuery({
    queryKey: ['task-stats'],
    queryFn: () => getTaskStatsStatsGet(),
    enabled: open,
    staleTime: 30 * 60 * 1000,
  })

  return (
    <>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger type="button" className="cursor-pointer">
          {children}
        </PopoverTrigger>
        <PopoverContent className="w-80 space-y-3">
          <div className="flex items-center gap-1.5">
            <p className="flex-1 truncate text-sm font-medium leading-tight">
              {paper.title ?? paper.filename}
            </p>
            <button
              type="button"
              disabled={isRunning}
              title="Re-run agents"
              onClick={() => setRerunOpen(true)}
              className="flex items-center justify-center size-6 shrink-0 rounded text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <RefreshCw className="size-3.5" />
            </button>
          </div>
          {tasksQuery.isPending ? (
            <div className="flex justify-center py-6">
              <Spinner />
            </div>
          ) : tasksQuery.isError ? (
            <p className="text-sm text-destructive">Could not load progress.</p>
          ) : (
            <TaskTimeline tasks={tasksQuery.data ?? []} stats={statsQuery.data} />
          )}
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            onClick={() => {
              setOpen(false)
              setDagOpen(true)
            }}
          >
            View pipeline
          </Button>
        </PopoverContent>
      </Popover>

      <RerunTaskDialog paper={paper} open={rerunOpen} onOpenChange={setRerunOpen} />

      <Dialog open={dagOpen} onOpenChange={setDagOpen}>
        <DialogContent className="!w-[32vw] !max-w-none h-[90vh]">
          <div className="flex flex-col h-full">
            <div className="border-b pb-4">
              <h2 className="text-lg font-semibold">{paper.title ?? paper.filename}</h2>
              <p className="text-sm text-muted-foreground">Pipeline execution</p>
            </div>
            <div className="flex-1 min-h-0 mt-4">
              <PaperTaskDAG paperId={paper.id} enabled={dagOpen} />
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
